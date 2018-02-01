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

from glob import glob

yaml = YAML()
yaml.allow_duplicate_keys = True

SINGULARITY_DESTINATION = "/data/0/cvmfs/singularity" # file destination for singularity containers
SINGULARITY_INSTALL = "/opt/singularity/bin/singularity" # location at which singularity is installed, could be something else like /usr/local/bin/singularity
QUAY_API_ENDPOINT = 'https://quay.io/api/v1/repository'

def get_quay_containers():
    """
    Gets all quay containers in the biocontainers repo
    # >>> lst = get_quay_containers()
    # >>> 'samtools:latest' in lst
    # True
    # >>> 'abricate:0.4--pl5.22.0_0' in lst
    # True
    # >>> 'samtools' in lst
    # False
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
    # >>> lst = get_singularity_containers()
    # >>> 'aragorn:1.2.36--1' in lst
    # True
    # >>> 'znc:latest' in lst
    # False

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
    # >>> lst = get_missing_containers()
    # >>> 'aragorn:1.2.36--1' in lst
    # False
    # >>> 'znc:latest' in lst
    # False
    # >>> 'pybigwig:0.1.11--py36_0' in lst
    # True
    # >>> 'samtools' in lst
    # False
    # >>> get_missing_containers(quay_list=[1, 2, 3, 'h', 'g', 'r'], singularity_list=[3, 4, 5], blacklist_file='blacklist.txt')
    # [1, 2, 'h']

    """
    blacklist = []
    if blacklist_file:
        blacklist = open(blacklist_file).read().split('\n')
    return [n for n in quay_list if n not in singularity_list and n not in blacklist]

def docker_to_singularity(container):
    """
    Convert docker to singularity container
    # >>> from glob import glob
    # >>> glob('%s/abundancebin:1.0.1--0' % SINGULARITY_DESTINATION)
    # []
    # >>> docker_to_singularity('abundancebin:1.0.1--0')
    # >>> glob('%s/abundancebin:1.0.1--0' % SINGULARITY_DESTINATION)
    # ['summat/abundancebin:1.0.1--0']
    """

    try:
        check_output("sudo %s build %s/%s docker://quay.io/biocontainers/%s && sudo rm -rf /root/.singularity/docker/" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, container, container), stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        error_info = {'code': e.returncode, 'cmd': e.cmd, 'out': e.output}
        return error_info
    else:
        return None


def get_test(container):
    """
    Downloading tarball from anaconda for test
    # >>> get_test('abundancebin:1.0.1--0')
    # {'commands': ['command -v abundancebin', 'abundancebin &> /dev/null || [[ "$?" == "255" ]]'], 'import_lang': 'python -c', 'container': 'abundancebin:1.0.1--0'}
    # >>> get_test('snakemake:3.11.2--py34_1')
    # {'commands': ['snakemake --help > /dev/null'], 'imports': ['snakemake'], 'import_lang': 'python -c', 'container': 'snakemake:3.11.2--py34_1'}
    # >>> get_test('perl-yaml:1.15--pl5.22.0_0')
    # {'imports': ['YAML', 'YAML::Any', 'YAML::Dumper', 'YAML::Dumper::Base', 'YAML::Error', 'YAML::Loader', 'YAML::Loader::Base', 'YAML::Marshall', 'YAML::Node', 'YAML::Tag', 'YAML::Types'], 'import_lang': 'perl -e', 'container': 'perl-yaml:1.15--pl5.22.0_0'}

    """
    package_tests = {}
    name = container.replace('--', ':').split(':') # list consisting of [name, version, (build, if present)]

    r = requests.get("https://anaconda.org/bioconda/%s/%s/download/linux-64/%s.tar.bz2" % (name[0], name[1], '-'.join(name)))
    
    try:
        tarball = tarfile.open(mode="r:bz2", fileobj=BytesIO(r.content))
    except tarfile.ReadError:
        pass
    else:

        try: # try to open meta.yam
            metafile = tarball.extractfile('info/recipe/meta.yaml')
            meta_yaml = yaml.load(metafile)
        except KeyError: # if it's not there ...
            logging.error("meta.yaml file not present.")
        else:
            try:
                if meta_yaml['test']['commands'] != [None]:
                    package_tests['commands'] = meta_yaml['test']['commands']
            except KeyError:
                pass

            try:
                if meta_yaml['test']['imports'] != [None]:
                    package_tests['imports'] = meta_yaml['test']['imports']
            except KeyError:
                pass
            
            #need to know what scripting languages are needed to run the container
            try:
                requirements = list(meta_yaml['requirements']['run'])
            except (KeyError, TypeError):
                pass
            else:
                for requirement in requirements:
                    if requirement.split()[0] == 'perl':
                        package_tests['import_lang'] = 'perl -e'
                        break
                    # elif ... :
                        # other languages if necessary ... hopefully python and perl should suffice though
                else: # python by default
                    package_tests['import_lang'] = 'python -c'

        if not package_tests: # if meta.yaml was not present or there were no tests in it, try and get run_test.sh instead
            try:
                run_test = tarball.extractfile('info/recipe/run_test.sh')
                package_tests['commands'] = run_test.read()
            except KeyError:
                logging.error("run_test.sh file not present.")

    package_tests['container'] = container
    return package_tests # {'commands': ...}


def mulled_get_test(container):
    """
    Gets test for hashed containers
    # >>> print(mulled_get_test('mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa:c17ce694dd57ab0ac1a2b86bb214e65fedef760e-0'))
    # {'commands': ['bamtools --help', 'samtools --help'], 'imports': [], 'container': 'mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa:c17ce694dd57ab0ac1a2b86bb214e65fedef760e-0', 'import_lang': 'python -c'}

    """

    package_tests = {'commands': [], 'imports': [], 'container': container, 'import_lang': 'python -c'}

    global github_hashes # ???

    github_hashes = json.loads(requests.get('https://api.github.com/repos/BioContainers/multi-package-containers/contents/combinations/').text)
    packages = []
    for item in github_hashes: # check if the container name is in the github repo
        if item['name'].split('.')[0] == container: # remove .tsv file ext before comparing name
            packages = requests.get(item['download_url']).text.split(',') # get names of packages from github
            packages = [package.split('=') for package in packages]

    containers = []
    for package in packages:
        r = requests.get("https://anaconda.org/bioconda/%s/files" % package[0])
        p = '-'.join(package)
        for line in r.text.split('\n'):
            if p in line:
                build = line.split(p)[1].split('.tar.bz2')[0]
                if build == "":
                    containers.append('%s:%s' % (package[0], package[1]))
                else:
                    containers.append('%s:%s-%s' % (package[0], package[1], build))
                break
    
    for container in containers:
        tests = get_test(container)
        package_tests['commands'] += tests.get('commands', [])
        for imp in tests.get('imports', []): # not a very nice solution but probably the simplest
            package_tests['imports'].append("%s 'import %s'" % (tests['import_lang'], imp)) 

    return package_tests

def test_singularity_container(tests):
    """
    Run tests, record if they pass or fail
    >>> results = test_singularity_container({'pybigwig:0.1.11--py36_0': {'imports': ['pyBigWig'], 'commands': ['python -c "import pyBigWig; assert(pyBigWig.numpy == 1); assert(pyBigWig.remote == 1)"'], 'import_lang': 'python -c'}, 'samtools:1.6--0': {'commands': ['samtools --help'], 'import_lang': 'python -c', 'container': 'samtools:1.6--0'}, 'yasm:1.3.0--0': {}})
    >>> 'samtools:1.6--0' in results['passed']
    True
    >>> results['failed'][0]['imports'] == ['pyBigWig']
    True
    >>> 'yasm:1.3.0--0' in results['notest']
    True
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
                        check_output("%s exec -H /tmp/foo %s/%s bash -c \"%s\"" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, container, command), stderr=subprocess.STDOUT, shell=True)
                    except subprocess.CalledProcessError as e1:
                        try:
                            check_output("%s exec -H /tmp/foo %s/%s %s" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, container, command), stderr=subprocess.STDOUT, shell=True)
                        except subprocess.CalledProcessError as e2:
                            errors.append({'command': command, 'output': e2.output})
                            test_passed = False
                        
            if test.get('imports', False):
                for imp in test['imports']:
                    try:
                        check_output("%s exec -H /tmp/foo %s/%s %s 'import %s'" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, container, test['import_lang'], imp), stderr=subprocess.STDOUT, shell=True)
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
                        help="Containers to be generated. If not given, all new additions to the quay biocontainers repository will be generated.")
    parser.add_argument('-nt', '--no-testing', dest='no_testing', action="store_true",
                        help="Skip testing of generated containers (not recommended).")
    parser.add_argument('-b', '--blacklist', dest='blacklist', default=None, 
                        help="Provide a 'blacklist file' containing containers which should not be processed.")
    parser.add_argument('-o', '--logfile', dest='logfile', default='singularity.log',
                        help="Filename for a log to be written to.")
    args = parser.parse_args()

    if not args.containers:
        containers = get_missing_containers(quay_list=get_quay_containers(), singularity_list=get_singularity_containers(), blacklist_file=args.blacklist)
    else:
        containers = args.containers

    with open(args.logfile, 'w') as f:
        f.write("SINGULARITY CONTAINERS GENERATED:")

        for container in containers:
            docker_to_singularity(container)

        if not args.no_testing:
            tests = {}
            for container in containers:
                if container[0:6] == 'mulled': # if it is a 'hashed container'
                    tests[container] = mulled_get_test(container)
                else:
                    tests[container] = get_test(container)
            test_results = test_singularity_container(tests)
    
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
    #main()
    import doctest
    doctest.testmod()