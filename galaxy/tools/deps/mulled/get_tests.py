#!/usr/bin/env python

"""
searches for tests for packages in the bioconda-recipes repo as well as on Anaconda, looking in different file locations. If no test can be found for the specified version, it will look for tests for other versions of the same package.
"""

from glob import glob
from ruamel.yaml import YAML
import requests
import tarfile
from io import BytesIO
from ruamel.yaml.scanner import ScannerError
yaml = YAML()
yaml.allow_duplicate_keys = True
import logging
from  jinja2 import Template
import json

def get_commands_from_yaml(file):
    """
    Gets tests from a yaml file
    """
    package_tests = {}

    try:
        meta_yaml = yaml.load(Template(file.read().decode('utf-8')).render()) # run the file through the jinja processing
    except ScannerError: # should not occur due to the above
        logging.info('ScannerError')
        return None
    try:
        if meta_yaml['test']['commands'] != [None] and meta_yaml['test']['commands'] != None:
            package_tests['commands'] = meta_yaml['test']['commands']
    except (KeyError, TypeError):
        logging.info('Error reading commands')
        pass
    try:
        if meta_yaml['test']['imports'] != [None] and meta_yaml['test']['imports'] != None:
            package_tests['imports'] = meta_yaml['test']['imports']
    except (KeyError, TypeError):
        logging.info('Error reading imports')
        pass
    
    if len(package_tests.get('commands', []) + package_tests.get('imports', [])) == 0:
        return None
    
    #need to know what scripting languages are needed to run the container
    try:
        requirements = list(meta_yaml['requirements']['run'])
    except (KeyError, TypeError):
        logging.info('Error reading requirements')
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
    return package_tests
    

def get_runtest(file):
    """
    Gets tests from a run_test.sh file

    """
    package_tests = {}
    package_tests['commands'] = [file.read().replace('\n', ' && ')]
    return package_tests


def get_anaconda_url(container):
    """
    Downloading tarball from anaconda for test
    """
    name = container.replace('--', ':').split(':') # list consisting of [name, version, (build, if present)]
    return "https://anaconda.org/bioconda/%s/%s/download/linux-64/%s.tar.bz2" % (name[0], name[1], '-'.join(name))


def get_test_from_anaconda(url):
    """
    Given the URL of an anaconda tarball, returns tests
    >>> get_test_from_anaconda('https://anaconda.org/bioconda/samtools/1.3.1/download/linux-64/samtools-1.3.1-5.tar.bz2')
    {'commands': ['samtools --help'], 'import_lang': 'python -c'}
    """
    r = requests.get(url)
    
    try:
        tarball = tarfile.open(mode="r:bz2", fileobj=BytesIO(r.content))
    except tarfile.ReadError:
        return None

    try:
        metafile = tarball.extractfile('info/recipe/meta.yaml')
    except (tarfile.ReadError, KeyError, TypeError):
        pass
    else:
        package_tests = get_commands_from_yaml(metafile)
        if package_tests:
            return package_tests

    # this part is probably unnecessary, but some of the older tarballs have a testfile with .yaml.template ext
    # try:
    #     metafile = tarball.extractfile('info/recipe/meta.yaml.template')
    # except (tarfile.ReadError, KeyError, TypeError):
    #     pass
    # else:
    #     package_tests = get_commands_from_yaml(metafile)
    #     if package_tests: 
    #         return package_tests

    # if meta.yaml was not present or there were no tests in it, try and get run_test.sh instead
    try: 
        run_test = tarball.extractfile('info/recipe/run_test.sh')
        return get_runtest(run_test)
    except KeyError:
        return None
        logging.info("run_test.sh file not present.")


def find_anaconda_versions(name):
    r = requests.get("https://anaconda.org/bioconda/%s/files" % name)
    urls = []
    for line in r.text.split('\n'):
        if 'download/linux' in line:
            urls.append(line.split('"')[1])
    return urls

def open_recipe_file(file):
	if RECIPES_REPO_PATH:
		return open('%s/%s' % (RECIPES_REPO_PATH, file))
	else: # if no clone of the repo is available locally, download from GitHub
		r = requests.get('https://raw.githubusercontent.com/bioconda/bioconda-recipes/master/%s' % recipes)
		if r.status_code == 404:
			raise IOError
		else:
			return r.text

def get_alternative_versions(filepath, filename):
	"""
	Returns files that match 'filepath/*/filename' in the bioconda-recipes repository
	>>> get_alternative_versions('recipes/samtools', 'meta.yaml')
	['recipes/samtools/0.1.12/meta.yaml', 'recipes/samtools/0.1.16/meta.yaml', 'recipes/samtools/0.1.17/meta.yaml', 'recipes/samtools/0.1.14/meta.yaml', 'recipes/samtools/0.1.13/meta.yaml', 'recipes/samtools/0.1.15/meta.yaml', 'recipes/samtools/0.1.19/meta.yaml', 'recipes/samtools/1.0/meta.yaml', 'recipes/samtools/0.1.18/meta.yaml', 'recipes/samtools/1.1/meta.yaml']

	"""
	if RECIPES_REPO_PATH:
		return [n.replace('%s/' % RECIPES_REPO_PATH, '') for n in glob('%s/%s/*/%s' % (RECIPES_REPO_PATH, filepath, filename))]
	# else use the GitHub API:
	versions = []
	r = json.loads(requests.get('https://api.github.com/repos/bioconda/bioconda-recipes/contents/%s' % filepath).content)
	for subfile in r:
		if subfile['type'] == 'dir':
			if requests.get('https://raw.githubusercontent.com/bioconda/bioconda-recipes/master/%s/%s' % (subfile['path'], filename)).status_code == 200:
				versions.append('%s/%s' % (subfile['path'], filename))
	return versions


def get_test(container):
    name = container.replace('--', ':').split(':')

    # first try meta.yaml in correct version folder

    try:
        t = get_commands_from_yaml(open_recipe_file('recipes/%s/%s/meta.yaml' % (name[0], name[1])))
    except IOError: 
        logging.info('/home/ubuntu/GitRepos/bioconda-recipes/recipes/%s/%s/meta.yaml could not be opened.' % (name[0], name[1]))
        t = None
    if t:
        t['container'] == container
        return t

    # try run_test in base folder

    try:
        t = get_runtest(open_recipe_file('recipes/%s/%s/run_test.sh' % (name[0], name[1])))
    except IOError: 
        logging.info('/home/ubuntu/GitRepos/bioconda-recipes/recipes/%s/%s/run_test.sh could not be opened.' % (name[0], name[1]))
        t = None
    if t:
        t['container'] == container
        return t

    # now try meta.yaml in base folder
    try:
        t = get_commands_from_yaml(open_recipe_file('recipes/%s/meta.yaml' % name[0]))
    except IOError: 
        logging.info('/home/ubuntu/GitRepos/bioconda-recipes/recipes/%s/meta.yaml could not be opened.' % name[0])
        t = None
    if t:
        t['container'] == container
        return t

    # try run_test in base folder

    try:
        t = get_runtest(open_recipe_file('recipes/%s/run_test.sh' % name[0]))
    except IOError: 
        logging.info('/home/ubuntu/GitRepos/bioconda-recipes/recipes/%s/run_test.sh could not be opened.' % name[0])
        t = None
    if t:
        t['container'] == container
        return t

    # try from anaconda

    t = get_test_from_anaconda(get_anaconda_url(container))
    if t:
        t['container'] == container
        return t
    logging.info('Nothing on anaconda.')
    # now try in incorrect version folders

    #g = glob('/home/ubuntu/GitRepos/bioconda-recipes/recipes/%s/*/meta.yaml' % container)
    g = get_alternative_versions('recipes/%s' % container, 'meta.yaml')
    for n in g:
        try:
            t = get_commands_from_yaml(open(n))
        except IOError:
            logging.info('No wrong versions (meta.yaml) either in recipes repo.')
            t = None
        if t:
            t['container'] == container
            return t

    # g = glob('/home/ubuntu/GitRepos/bioconda-recipes/recipes/%s/*/run_test.sh')
    g = get_alternative_versions('recipes/%s' % container, 'run_test.sh')
    for n in g:
        try:
            t = get_commands_from_yaml(open(n))
        except IOError:
            logging.info('No wrong versions (run_test.sh) either in recipes repo.')
            t = None
        if t:
            t['container'] == container
            return t

    g = find_anaconda_versions(container)
    for n in g:
        t = get_test_from_anaconda(n)
        if t:
            t['container'] == container
            return t
    logging.info('And no wrong versions in anaconda.')
            
    return {}

######################################
########## MAIN STARTS HERE ##########
######################################

RECIPES_REPO_PATH = '/home/simon/GitRepos/bioconda-recipes' # can also be None; then the the repository will be accessed via github

# tests = {}
# for n in ls:
#     print(n)
#     tests[n] = get_test(n)
#     print(tests[n])

# print(tests)


import doctest
doctest.testmod()
