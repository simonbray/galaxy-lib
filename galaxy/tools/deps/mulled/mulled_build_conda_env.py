#!/usr/bin/env python
import requests
import json
import argparse
import logging

from galaxy.tools.deps.conda_util import install_conda_targets, CondaContext, CondaTarget

class EnvRequest():
    """
    Takes the name of a docker container and returns a conda environment.
    """
    
    def __init__(self, container_name):
        self.container = container_name
        self.conda_context = CondaContext(ensure_channels='bioconda')
        #print self.container[0:6] == 'mulled'
        if self.container[0:6] != 'mulled': # check if a hash is requested or a single package
            self.packages = [self.container]
        else:
            self.packages = self.get_packages_from_hash()

    def get_packages_from_hash(self):
        """
        If self.container is a hash, check what packages it refers to using GitHub.
        """
        github_hashes = json.loads(requests.get('https://api.github.com/repos/BioContainers/multi-package-containers/contents/combinations/').text)
        for item in github_hashes: # check if the container name is in the github repo
            if item['name'][0:50] == self.container:
                packages = requests.get(item['download_url']).text.split(',') # get names of packages from github
                packages = [package.split('=')[0] for package in packages] # remove versions
                return packages
        logging.error("Container name not recognized.")

    def install_env(self):
        """
        Install a conda environment with the requested package(s).
        """
        if self.packages == None: # if the container was not available
            return None
        targets = [CondaTarget(package) for package in self.packages] # create a target object for each package
        install_conda_targets(targets, self.conda_context, env_name="".join(["__", self.container])) # create and install the env

def main():
    parser = argparse.ArgumentParser(description='Generates a conda environment from a Docker container name.')
    parser.add_argument('container', help='Give the name of the Docker container.')
    args = parser.parse_args()

    env = EnvRequest(args.container)
    env.install_env()

if __name__ == "__main__":
    main()