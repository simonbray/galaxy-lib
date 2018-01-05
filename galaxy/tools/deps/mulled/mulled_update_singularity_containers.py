import requests
from lxml import html
import subprocess
import tarfile
from ruamel.yaml import YAML
from io import BytesIO
yaml = YAML()
yaml.allow_duplicate_keys = True

SINGULARITY_DESTINATION = "summat" # file destination for singularity containers
SINGULARITY_INSTALL = "/usr/local/bin/singularity" # location at which singularity is installed, could be something else like /usr/local/bin/singularity

def get_quay_containers():
    """
    Gets all quay containers in the biocontainers repo
    """
	containers = []
	root_endpoint = 'https://quay.io/api/v1/repository'

	repos_parameters = {'public': 'true', 'namespace': 'biocontainers'}
	repos_headers ={'Accept-encoding': 'gzip', 'Accept': 'application/json'}
	repos_response = requests.get(root_endpoint, headers=repos_headers, params=repos_parameters, timeout=12)

	repos = repos_response.json()['repositories']
	#repos = [n['name'] for n in repos]
	
	for repo in repos:
		tags_response = requests.get("%s/biocontainers/%s" % (root_endpoint, repo['name']))
		tags = tags_response.json()['tags']
		for tag in tags:
			containers.append('%s:%s' % (repo['name'], tag))

	return containers

def get_singularity_containers():
	"""
	Gets all existing singularity containers from "https://depot.galaxyproject.org/singularity/"
	"""
	index_url = "https://depot.galaxyproject.org/singularity/"
	index = requests.get(index_url)
	#l = response.text.split('\n')
	tree = html.fromstring(index.content)
	containers = tree.xpath('//a/text()')
	return containers

def get_missing_containers(quay_list=get_quay_containers(), singularity_list=get_singularity_containers()):
	"""
	Returns list of quay containers that do not exist as singularity containers
	"""
	return [n for n in quay_list if not in singularity_list]

def docker_to_singularity(container):
	"""
	Convert docker to singularity container
	"""
	process = subprocess.Popen("/bin/bash", shell=False, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)							 
	#commands = "sudo singularity build ~/%s docker://quay.io/biocontainers/%s && sudo rm -rf /root/.singularity/docker/ && sudo chown ubuntu %s && mv %s %s" % (4*(container,) + (SINGULARITY_DESTINATION,))
	commands = "sudo singularity build %s/%s docker://quay.io/biocontainers/%s && echo exit_code$?exit_code && sudo rm -rf /root/.singularity/docker/" % (SINGULARITY_DESTINATION, container, container)
	out, err = process.communicate(commands)
	exit_code = out.split('exit_code')[1]
	print(exit_code)
	if exit_code == '0':
		return None
	else:	
		return out, err

def get_test(container):
    """
    Downloading tarball from anaconda for test
    """
    package_tests = {}
    name, version, build = container.replace('--', ':').split(':')

    r = requests.get("https://anaconda.org/bioconda/%s/%s/download/linux-64/%s-%s-%s.tar.bz2" % (name, version, name, version, build))
    tarball = tarfile.open(mode="r:bz2", fileobj=BytesIO(r.content))
    
    try: # try to open meta.yam
        metafile = tarball.extractfile('info/recipe/meta.yaml')
        meta_yaml = yaml.load(metafile)
    except KeyError: # if it's not there ...
        pass
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
            requirements = meta_yaml['requirements']['run']
        except KeyError:
            pass
        else:
            for requirement in requirements:
                if requirement.split(' ')[0] == 'perl':
                    package_tests['import_lang'] = 'perl -e'
                    break
                # elif ... :
                    # other languages if necessary ... hopefully python and perl should suffice though
                else: # python by default
                    package_tests['import_lang'] = 'python -c'

    if package_tests == {}: # if meta.yaml was not present or there were no tests in it, try and get run_test.sh instead
        try:
            run_test = tarball.extractfile('info/recipe/run_test.sh')
            package_tests['commands'] = run_test.read()
        except KeyError:
            pass

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
			try:
				test['commands']
			except KeyError:
				pass
			else:
				for command in test['commands']:
					command = command.replace('$PREFIX', '/usr/local/')
					command = command.replace('${PREFIX}', '/usr/local/')
					command = command.replace('$R ', 'Rscript ')
					
					process = subprocess.Popen("/bin/bash", shell=False, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)                             
					inp = "%s exec -H /tmp/foo %s/%s bash -c \"%s\"\necho $?" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, test['container'], command)
					out, err = process.communicate(inp)
					if out.split('\n')[-2] != '0':
						# executing via bash -c command causes some tests to fail - therefore, it is also tried without
						process = subprocess.Popen("/bin/bash", shell=False, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)                             
						inp = "%s exec -H /tmp/foo %s/%s %s\necho $?" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, test['container'], command)
						out, err = process.communicate(inp)
						if out.split('\n')[-2] != '0':
							test_passed = False	
							errors.append({'command': test, 'output': out, 'error': err})
			try:
				test['imports']
			except KeyError:
				pass
			else:
				for imp in test['imports']:
					process = subprocess.Popen("/bin/bash", shell=False, universal_newlines=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)                             
					inp = "%s exec -H /tmp/foo %s/%s %s 'import %s'\necho $?" % (SINGULARITY_INSTALL, SINGULARITY_DESTINATION, test['container'], test['import_lang'], imp)
					out, err = process.communicate(inp)
					if out.split('\n')[-2] != '0':
						test_passed = False
						errors.append({'import': test, 'output': out, 'error': err})
				
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

    test_singularity_container(test_results)

if __name__ == "__main__":
    main()