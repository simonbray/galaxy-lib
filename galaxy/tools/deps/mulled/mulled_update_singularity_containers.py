#!/usr/bin/env python

import requests
from lxml import html
import subprocess
import tarfile
from ruamel.yaml import YAML
from io import BytesIO
#from mulled_build import check_output
from subprocess import check_output
import logging
from shutil import copy
import pickle
import json
import argparse
from jinja2 import Template
from get_tests import test_search, hashed_test_search
from glob import glob

yaml = YAML()
yaml.allow_duplicate_keys = True

#installation = "/opt/singularity/bin/singularity" # location at which singularity is installed, could be something else like /usr/local/bin/singularity
QUAY_API_ENDPOINT = 'https://quay.io/api/v1/repository'

def get_quay_containers():
    """
    Gets all quay containers in the biocontainers repo
    >>> lst = get_quay_containers()
    >>> 'samtools:latest' in lst
    True
    >>> 'abricate:0.4--pl5.22.0_0' in lst
    True
    >>> 'samtools' in lst
    False
    """
    containers = []

    repos_parameters = {'public': 'true', 'namespace': 'biocontainers'}
    repos_headers ={'Accept-encoding': 'gzip', 'Accept': 'application/json'}
    repos_response = requests.get(QUAY_API_ENDPOINT, headers=repos_headers, params=repos_parameters, timeout=12)

    repos = repos_response.json()['repositories']
    #repos = [n['name'] for n in repos]

    for repo in repos:
        logging.info(repo)
        tags_response = requests.get("%s/biocontainers/%s" % (QUAY_API_ENDPOINT, repo['name']))
        tags = tags_response.json()['tags']
        for tag in tags:
            containers.append('%s:%s' % (repo['name'], tag))

    return containers

def get_singularity_containers():
    """
    Gets all existing singularity containers from "https://depot.galaxyproject.org/singularity/"
    >>> lst = get_singularity_containers()
    >>> 'aragorn:1.2.36--1' in lst
    True
    >>> 'znc:latest' in lst
    False

    """
    index_url = "https://depot.galaxyproject.org/singularity/"
    index = requests.get(index_url)
    #l = response.text.split('\n')
    tree = html.fromstring(index.content)
    containers = tree.xpath('//a/@href')
    containers = [container.replace('%3A', ':') for container in containers]
    return containers

def get_missing_containers(quay_list, singularity_list, blacklist_file=None):
    """
    Returns list of quay containers that do not exist as singularity containers. Files stored in a blacklist will be ignored

    >>> import tempfile
    >>> blacklist = tempfile.NamedTemporaryFile(delete=False)
    >>> blacklist.write('l\\n\\ng\\nn\\nr')
    >>> blacklist.close()
    >>> get_missing_containers(quay_list=['1', '2', '3', 'h', 'g', 'r'], singularity_list=['3', '4', '5'], blacklist_file=blacklist.name)
    ['1', '2', 'h']
    """
    blacklist = []
    if blacklist_file:
        blacklist = open(blacklist_file).read().split('\n')
    return [n for n in quay_list if n not in singularity_list and n not in blacklist]

def get_container_list_from_file(filename):
    """
    Returns a list of containers stored in a file (one on each line)
    >>> import tempfile
    >>> listfile = tempfile.NamedTemporaryFile(delete=False)
    >>> listfile.write('bbmap:36.84--0\\nbiobambam:2.0.42--0\\nconnor:0.5.1--py35_0\\ndiamond:0.8.26--0\\nedd:1.1.18--py27_0')
    >>> listfile.close()
    >>> get_container_list_from_file(listfile.name)
    ['bbmap:36.84--0', 'biobambam:2.0.42--0', 'connor:0.5.1--py35_0', 'diamond:0.8.26--0', 'edd:1.1.18--py27_0']
    >>> 
    """
    return open(filename).read().split('\n')
   
def docker_to_singularity(container, installation, filepath):
    """
    # Convert docker to singularity container
    # >>> from glob import glob
    # >>> glob('%s/abundancebin:1.0.1--0' % filepath)
    # []
    # >>> docker_to_singularity('abundancebin:1.0.1--0')
    # >>> glob('%s/abundancebin:1.0.1--0' % filepath)
    # ['summat/abundancebin:1.0.1--0']
    """

    try:
        check_output("sudo %s build %s/%s docker://quay.io/biocontainers/%s && sudo rm -rf /root/.singularity/docker/" % (installation, filepath, container, container), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        error_info = {'code': e.returncode, 'cmd': e.cmd, 'out': e.output}
        return error_info
    else:
        return None

def test_singularity_container(tests, installation, filepath):
    """
    # Run tests, record if they pass or fail
    # >>> results = test_singularity_container({'pybigwig:0.1.11--py36_0': {'imports': ['pyBigWig'], 'commands': ['python -c "import pyBigWig; assert(pyBigWig.numpy == 1); assert(pyBigWig.remote == 1)"'], 'import_lang': 'python -c'}, 'samtools:1.6--0': {'commands': ['samtools --help'], 'import_lang': 'python -c', 'container': 'samtools:1.6--0'}, 'yasm:1.3.0--0': {}})
    # >>> 'samtools:1.6--0' in results['passed']
    # True
    # >>> results['failed'][0]['imports'] == ['pyBigWig']
    # True
    # >>> 'yasm:1.3.0--0' in results['notest']
    # True
    """
    test_results = {'passed': [], 'failed': [], 'notest': []}
    for container, test in tests.items():
        if 'commands' not in test and 'imports' not in test:
            test_results['notest'].append(container)

        else:
            test_passed = True
            errors = []
            if test.get('commands', False):
                for command in test['commands']:
                    command = command.replace('$PREFIX', '/usr/local/')
                    command = command.replace('${PREFIX}', '/usr/local/')
                    command = command.replace('$R ', 'Rscript ')
                    
                    try:
                        check_output("%s exec -H /tmp/foo %s/%s bash -c \"%s\"" % (installation, filepath, container, command), stderr=subprocess.STDOUT, shell=True)
                    except subprocess.CalledProcessError as e1:
                        try:
                            check_output("%s exec -H /tmp/foo %s/%s %s" % (installation, filepath, container, command), stderr=subprocess.STDOUT, shell=True)
                        except subprocess.CalledProcessError as e2:
                            errors.append({'command': command, 'output': e2.output})
                            test_passed = False
                        
            if test.get('imports', False):
                for imp in test['imports']:
                    try:
                        check_output("%s exec -H /tmp/foo %s/%s %s 'import %s'" % (installation, filepath, container, test['import_lang'], imp), stderr=subprocess.STDOUT, shell=True)
                    except subprocess.CalledProcessError as e:
                        errors.append({'import': imp, 'output': e.output})
                        test_passed = False

            if test_passed:
                test_results['passed'].append(container)
            else:
                test['errors'] = errors
                test_results['failed'].append(test)
    return test_results

def main():
    parser = argparse.ArgumentParser(description='Updates index of singularity containers.')
    parser.add_argument('-c', '--containers', dest='containers', nargs='+', default=None,
                        help="Containers to be generated. If the number of containers is large, it may be simpler to use the --containers-list option.")
    parser.add_argument('-l', '--container-list', dest='container_list', default=None,
                        help="Name of file containing list of containers to be generated. Alternative to --containers.")
    parser.add_argument('-a', '--all', dest='all', default=False,
                        help="All new additions to the quay biocontainers repository will be generated.")
    parser.add_argument('-nt', '--no-testing', dest='no_testing', action="store_true",
                        help="Skip testing of generated containers (not recommended).")
    parser.add_argument('-b', '--blacklist', dest='blacklist', default=None, 
                        help="To be used in combination with --all; provide a 'blacklist file' containing containers which should not be processed.")
    parser.add_argument('-o', '--logfile', dest='logfile', default='singularity.log',
                        help="Filename for a log to be written to.")
    parser.add_argument('-f', '--filepath', dest='filepath',
                        help="File path where newly-built Singularity containers are placed.")
    parser.add_argument('-i', '--installation', dest='installation',
                        help="File path of Singularity installation.")
    parser.add_argument('--deep-search', dest='deep_search', default=False,
                        help="Perform a more extensive, but probably slower, search for tests.")
    parser.add_argument('--anaconda-channel', dest='anaconda_channel', default='bioconda',
                        help="Anaconda channel to search for tests (default: bioconda).")
    parser.add_argument('--github-repo', dest='github_repo',
                        help="Github repository to search for tests - only relevant if --deep-search is activated (default: bioconda/bioconda-recipes")
    parser.add_argument('--github-local-path', dest='github_local_path', default=None,
                        help="If the bioconda-recipes repository (or other repository containing tests) is available locally, provide the path here. Only relevant if --deep-search is activated.")

    args = parser.parse_args()

    if args.containers:
        containers = args.containers
    elif args.container_list:
        containers = get_container_list_from_file(args.containers)
    elif args.all:
        containers = get_missing_containers(quay_list=get_quay_containers(), singularity_list=get_singularity_containers(), blacklist_file=args.blacklist)
    else:
        print("One of --containers, --container-list, or --all should be selected.")
        return

    with open(args.logfile, 'w') as f:
        f.write("SINGULARITY CONTAINERS GENERATED:")

        for container in containers:
            docker_to_singularity(container, args.installation, args.filepath)

        if not args.no_testing:
            tests = {}
            for container in containers:
                if container[0:6] == 'mulled': # if it is a 'hashed container'
                    tests[container] = hashed_test_search(container, args.github_local_path, args.deep_search, args.anaconda_channel, args.github_repo)
                else:
                    tests[container] = test_search(container, args.github_local_path, args.deep_search, args.anaconda_channel, args.github_repo)
            test_results = test_singularity_container(tests, args.installation, args.filepath)
    
            f.write('\n\tTEST PASSED:')
            for container in test_results['passed']:
                f.write('\n\t\t%s' % container)
            f.write('\n\tTEST FAILED:')
            for container in test_results['failed']:
                f.write('\n\t\t%s' % container['container'])
                for error in container['errors']:
                    f.write('\n\t\t\tCOMMAND: %s\n\t\t\t\tERROR:%s' % (error.get('command', 'import' + error.get('import', 'nothing found')), error['output']))                
            f.write('\n\tNO TEST AVAILABLE:')
            for container in test_results['notest']:
                f.write('\n\t\t%s' % container)
        else:
            for container in containers:
                f.write('\n\t%s' % container)

if __name__ == "__main__":
    main()
    # import doctest
    # doctest.testmod()