import requests
from lxml import html
import subprocess
import tarfile
from ruamel.yaml import YAML
from io import BytesIO
#from mulled_build import check_output
from subprocess import check_output
import logging


yaml = YAML()
yaml.allow_duplicate_keys = True

SINGULARITY_DESTINATION = "summat" # file destination for singularity containers
SINGULARITY_INSTALL = "/usr/local/bin/singularity" # location at which singularity is installed, could be something else like /usr/local/bin/singularity
QUAY_API_ENDPOINT = 'https://quay.io/api/v1/repository'

# def get_quay_containers():
#     """
#     Gets all quay containers in the biocontainers repo
#     """
#     containers = []

#     repos_parameters = {'public': 'true', 'namespace': 'biocontainers'}
#     repos_headers ={'Accept-encoding': 'gzip', 'Accept': 'application/json'}
#     repos_response = requests.get(QUAY_API_ENDPOINT, headers=repos_headers, params=repos_parameters, timeout=12)

#     repos = repos_response.json()['repositories']
#     #repos = [n['name'] for n in repos]
    
#     for repo in repos:
#         tags_response = requests.get("%s/biocontainers/%s" % (QUAY_API_ENDPOINT, repo['name']))
#         tags = tags_response.json()['tags']
#         for tag in tags:
#             containers.append('%s:%s' % (repo['name'], tag))

#     return containers

# def get_singularity_containers():
#     """
#     Gets all existing singularity containers from "https://depot.galaxyproject.org/singularity/"
#     """
#     index_url = "https://depot.galaxyproject.org/singularity/"
#     index = requests.get(index_url)
#     #l = response.text.split('\n')
#     tree = html.fromstring(index.content)
#     containers = tree.xpath('//a/text()')
#     return containers

# def get_missing_containers(quay_list=get_quay_containers(), singularity_list=get_singularity_containers()):
#     """
#     Returns list of quay containers that do not exist as singularity containers
#     """
#     return [n for n in quay_list if n not in singularity_list]

def docker_to_singularity(container):
    """
    Convert docker to singularity container
    """

    try:
        check_output("sudo singularity build %s/%s docker://quay.io/biocontainers/%s && sudo rm -rf /root/.singularity/docker/" % (SINGULARITY_DESTINATION, container, container), stderr=subprocess.STDOUT, shell=True)
    	#check_output("echo %s" % container , stderr=subprocess.STDOUT, shell=True)
    except subprocess.CalledProcessError as e:
        error_info = {'code': e.returncode, 'cmd': e.cmd, 'out': e.output}
        return error_info
    else:
        return None


def get_test(container):
    """
    Downloading tarball from anaconda for test
    """
    package_tests = {}
    name = container.replace('--', ':').split(':') # list consisting of [name, version, (build, if present)]

    r = requests.get("https://anaconda.org/bioconda/%s/%s/download/linux-64/%s.tar.bz2" % (name[0], name[1], '-'.join(name)))
    tarball = tarfile.open(mode="r:bz2", fileobj=BytesIO(r.content))
    
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

def test_singularity_container(tests):
    """
    Run tests, record if they pass or fail
    """
    test_results = {'passed': [], 'failed': [], 'notest': []}
    for test in tests:
        if 'commands' not in test and 'imports' not in test:
            test_results['notest'].append(test['container'])

        else:
            test_passed = True
            errors = []
            if test.get('commands', False):
                for command in test['commands']:
                    command = command.replace('$PREFIX', '/usr/local/')
                    command = command.replace('${PREFIX}', '/usr/local/')
                    command = command.replace('$R ', 'Rscript ')
                    
                    try:
                        check_output("%s exec -H /tmp/foo %s/%s bash -c \"%s\"" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, test['container'], command), stderr=subprocess.STDOUT, shell=True)
                    except subprocess.CalledProcessError as e1:
                        try:
                            check_output("%s exec -H /tmp/foo %s/%s %s" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, test['container'], command), stderr=subprocess.STDOUT, shell=True)
                        except subprocess.CalledProcessError as e2:
                            errors.append({'command': test, 'output': e1.output})
                            test_passed = False
                        
            if test.get('imports', False):
                for imp in test['imports']:
                    try:
                        check_output("%s exec -H /tmp/foo %s/%s %s 'import %s'" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, test['container'], test['import_lang'], imp), stderr=subprocess.STDOUT, shell=True)
                    except subprocess.CalledProcessError as e:
                        errors.append({'import': test, 'output': e.output})
                        test_passed = False

            if test_passed:
                test_results['passed'].append(test)
            else:
                test['errors'] = errors
                test_results['failed'].append(test)
    return test_results

def main():
    
    parser = argparse.ArgumentParser(description='Updates index of singularity containers.')
    parser.add_argument()
    args = parser.parse_args()

    #get_quay_containers()
    #get_singularity_containers()

    containers = get_missing_containers()
    tests = []

    for container in containers:
        docker_to_singularity(container)
        test = get_test(container)
        tests.append(tests)

    test_singularity_container(tests)

if __name__ == "__main__":
    main()