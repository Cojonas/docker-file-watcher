#!/usr/bin/env python3

import os, shutil, docker, time

from multiprocessing import Process

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from docker.types import Mount

from threading import Timer

from dotenv import load_dotenv
load_dotenv()


import signal





def makeDefaultFolder():
    BASE_DIR =  os.path.dirname(os.path.realpath(__file__))
    IMAGE_DIR = os.path.join(BASE_DIR, "images")
    try:
        os.mkdir(IMAGE_DIR)
        return IMAGE_DIR
    except FileExistsError:
        return IMAGE_DIR
        

DIRECTORY_TO_WATCH = os.getenv("WATCH_DIR", makeDefaultFolder())
PORT_EXTERNAL = os.getenv('PORT_EXTERNAL', 80)
PORT_INTERNAL = os.environ["PORT_INTERNAL"] 
CONTAINER_NAME = os.environ["CONTAINER_NAME"]

#default shared folder is current directory
SHARED_FOLDER_DOCKER = os.environ["SHARED_FOLDER_DOCKER"]

DOCKERIMAGE_FILENAME = os.getenv('DOCKERIMAGE_FILENAME', "dockerimage.tar")



def deleteFolderContent(folder):
    for the_file in os.listdir(folder):
        file_path = os.path.join(folder, the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            #elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            print(e)

def debounce(wait):
    """ Decorator that will postpone a functions
        execution until after wait seconds
        have elapsed since the last time it was invoked. """
    def decorator(fn):
        def debounced(*args, **kwargs):
            def call_it():
                fn(*args, **kwargs)
            try:
                debounced.t.cancel()
            except(AttributeError):
                pass
            debounced.t = Timer(wait, call_it)
            debounced.t.start()
        return debounced
    return decorator


class Watcher:

    def __init__(self, dockerManager):
        self.observer = Observer()
        self.dockerManager = dockerManager
        signal.signal(signal.SIGINT, self.keyboardInterruptHandler)
    
    def keyboardInterruptHandler(self, signal, frame):
        self.dockerManager.stop_container()
        exit(0)

    def run(self):
        event_handler = Handler(self.dockerManager)
        self.observer.schedule(event_handler, DIRECTORY_TO_WATCH, recursive=True)
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except:
            self.observer.stop()
            print("Error")

        self.observer.join()
            


class DockerManager: 
    def __init__(self):
        self.client = docker.from_env()
        self.mount = Mount(target=SHARED_FOLDER_DOCKER, source=DIRECTORY_TO_WATCH, type="bind")
        self.run_container()

    def run_container(self):
        print("running container")
        ports = {}
        ports[str(PORT_EXTERNAL) + "/tcp"] = PORT_INTERNAL 
        self.container = self.client.containers.run(CONTAINER_NAME, ports=ports, environment=["SHARED_FOLDER_DOCKER=" + SHARED_FOLDER_DOCKER], mounts=[self.mount], detach=True)
        print(self.container.logs())


    def stop_container(self):
        print("stopping container")
        self.container.stop()

    def restart_container(self):
        print("restarting container")
        if self.load_container():
            self.container.restart()

    def load_container(self):
        print("loading new image...")
        images = list()
        fileName = DIRECTORY_TO_WATCH + "dockerimage.tar"
        print(fileName)
        with open(DIRECTORY_TO_WATCH + "dockerimage.tar", "rb") as file:
            try:
                images = self.client.images.load(file)
            except docker.errors.ImageLoadError:
                print("image load error")
                return False
        print("loaded " + str(images))
        return True


dockerManager = DockerManager()

class Handler(FileSystemEventHandler):

    def __init__(self, dockerManager):
        super().__init__()
        self.dockerManager = dockerManager
        
    
    def on_any_event(self, event):
        if event.is_directory:
            return None

        elif event.event_type == 'created':
            # Take any action here when a file is first created.
            print("Received created event - %s." % event.src_path)



        elif event.event_type == 'modified':
            ## debounce function
            self.triggerReload()

    @debounce(3)
    def triggerReload(self):
        dockerManager.stop_container()
        if self.dockerManager.load_container():
            self.dockerManager.run_container()
        #else self.dockerManager.run_container()

if __name__ == '__main__':

    deleteFolderContent(DIRECTORY_TO_WATCH)
    
    w = Watcher(dockerManager)
    w.run()
