#!/usr/bin/env python
from mulled_list import get_quay_containers
from get_tests import test_search, hashed_test_search
from mulled_update_singularity_containers import get_list_from_file
import subprocess
#from mulled_build import check_output
from subprocess import check_output
import logging
from glob import glob
import argparse

def extract_env_from_container(container, filepath, no_sudo=False): #container as name:build--version
    """
    Convert docker to singularity container
    # >>> from glob import glob
    # >>> glob('%s/__abundancebin@1.0.1--0' % filepath)
    # []
    # >>> extract_env_from_container('abundancebin:1.0.1--0')
    # >>> glob('%s/__abundancebin@1.0.1' % filepath)
    # ['/home/ubuntu/condaenvs/__abundancebin@1.0.1']
    """

    envname = '__%s' % '@'.join(container.split('--')[0].split(':'))
    try:
        if no_sudo:
            check_output("cid=`docker run -d quay.io/biocontainers/%s` && docker cp $cid:/usr/local/ %s/%s && docker stop $cid && docker rm $(docker ps -a -q) && docker rmi $(docker images -q)" % (container, filepath, envname), shell=True)
        else:
            check_output("cid=`docker run -d quay.io/biocontainers/%s` && sudo docker cp $cid:/usr/local/ %s/%s && docker stop $cid && docker rm $(docker ps -a -q) && docker rmi $(docker images -q)" % (container, filepath, envname), shell=True)
    except subprocess.CalledProcessError as e:
        error_info = {'code': e.returncode, 'cmd': e.cmd, 'out': e.output, 'container': container}
        return error_info
    else:
        return None

def test_conda_env(tests):
    """
    # Run tests, record if they pass or fail
    # >>> results = test_conda_env({'__samtools@latest': {'commands': ['samtools --help'], 'import_lang': 'python -c'}, '__pybigwig@0.1.11--py36_0': {'imports': ['pyBigWig'], 'commands': ['python -c "import pyBigWig; assert(pyBigWig.numpy == 1); assert(pyBigWig.remote == 1)"'], 'import_lang': 'python -c'}, '__yasm@1.3.0--0': {}})
    # >>> 'pyBigWig' in results['failed'][0]['imports']
    # True
    # >>> '__samtools@latest' in results['passed']
    # True
    # >>> '__yasm@1.3.0--0' in results['notest']
    # True

    """
    test_results = {'passed': [], 'failed': [], 'notest': []}

    for env, test in tests.items():
        if 'commands' not in test and 'imports' not in test:
            test_results['notest'].append(env)

        else:
            test_passed = True
            errors = []
            if test.get('commands', False):
                for command in test['commands']:
                    command = command.replace('$PREFIX', '/usr/local/')
                    command = command.replace('${PREFIX}', '/usr/local/')
                    command = command.replace('$R ', 'Rscript ')
                    
                    try:
                        check_output("source activate %s && bash -c \"%s\"" % (env, command), shell=True, executable='/bin/bash')
                    except subprocess.CalledProcessError as e1:
                        try:
                            check_output("source activate %s && %s" % (env, command), shell=True, executable='/bin/bash')
                        except subprocess.CalledProcessError as e2:
                            errors.append({'command': command, 'output': e2.output})
                            test_passed = False

            if test.get('imports', False):
                for imp in test['imports']:
                    try:
                        check_output("source activate %s && %s 'import %s'" % (env, test['import_lang'], imp), stderr=subprocess.STDOUT, shell=True, executable='/bin/bash')
                    except subprocess.CalledProcessError as e:
                        errors.append({'import': imp, 'output': e.output})
                        test_passed = False

            if test_passed:
                test_results['passed'].append(env)
            else:
                test['errors'] = errors
                test_results['failed'].append(test)
    logging.info(test_results)
    return test_results

def main():
    parser = argparse.ArgumentParser(description='Updates index of conda environments.')
    parser.add_argument('-e', '--environments', dest='envs', nargs='+', default=None,
                        help="Environments to be generated. If not given, all new additions to the quay biocontainers repository will be generated.")
    parser.add_argument('-l', '--environment-list', dest='environment_list', default=None,
                        help="Name of file containing list of environments to be generated. Alternative to --environments.")
    parser.add_argument('-f', '--filepath', dest='filepath',
                        help="File path where conda environments are stored.")
    parser.add_argument('--no-sudo', dest='no_sudo', action='store_true',
                        help="Build environments without sudo.")
    parser.add_argument('--testing', '-t', dest='testing', default=None,
                        help="Performs testing automatically - a name for the output file should be provided. (Alternatively, testing may be done using the separate testing tool.")

    args = parser.parse_args()

    if args.envs:
        envs = args.envs
    elif args.environment_list:
        envs = get_list_from_file(args.environment_list)
    else:
        print("Either --environments or --environment-list should be selected.")
        return

    for env in envs:
        extract_env_from_container(env, args.filepath)

    if args.testing:
        test({'anaconda_channel': 'bioconda', 'filepath': args.filepath, 'github_repo': 'bioconda/bioconda-recipes', 'deep_search': False, 'github_local_path': None, 'logfile': args.testing, 'environments': environments})

        test()

def test(args=None):
    if not args: # i.e. if testing is called directly from CLI and not via main()
        parser = argparse.ArgumentParser(description='Tests.')
        parser.add_argument('-e', '--environments', dest='envs', nargs='+', default=None,
                            help="Environments to be generated. If not given, all new additions to the quay biocontainers repository will be generated.")
        parser.add_argument('-l', '--environment-list', dest='environment_list', default=None,
                            help="Name of file containing list of environments to be generated. Alternative to --environments.")
        parser.add_argument('-f', '--filepath', dest='filepath',
                            help="File path where conda environments are stored.")
        parser.add_argument('-o', '--logfile', dest='logfile', default='conda.log',
                            help="Filename for a log to be written to.")
        parser.add_argument('--deep-search', dest='deep_search', default=False,
                            help="Perform a more extensive, but probably slower, search for tests.")
        parser.add_argument('--anaconda-channel', dest='anaconda_channel', default='bioconda',
                            help="Anaconda channel to search for tests (default: bioconda).")
        parser.add_argument('--github-repo', dest='github_repo',
                            help="Github repository to search for tests - only relevant if --deep-search is activated (default: bioconda/bioconda-recipes")
        parser.add_argument('--github-local-path', dest='github_local_path', default=None,
                            help="If the bioconda-recipes repository (or other repository containing tests) is available locally, provide the path here. Only relevant if --deep-search is activated.")
        args = vars(parser.parse_args())
    if args['envs']:
        envs = args['envs']
    elif args['environment_list']:
        envs = get_list_from_file(args['environment_list'])
    else:
        print("Either --environments or --environment-list should be selected.")
        return

    with open(args['logfile'], 'w') as f:
        f.write("CONDA ENVIRONMENTS GENERATED:")
        tests = {}
        for env in envs:
            if env[0:6] == 'mulled': # if it is a 'hashed container'
                tests['__%s' % env.split('--')[0].replace(':', '@')] = hashed_test_search(env, args['github_local_path'], args['deep_search'], args['anaconda_channel'], args['github_repo'])
            else:
                tests['__%s' % env.split('--')[0].replace(':', '@')] = test_search(env, args['github_local_path'], args['deep_search'], args['anaconda_channel'], args['github_repo'])
        test_results = test_conda_env(tests)

        f.write('\n\tTEST PASSED:')
        for env in test_results['passed']:
            f.write('\n\t\t%s' % env)
        f.write('\n\tTEST FAILED:')
        for env in test_results['failed']:
            f.write('\n\t\t%s' % env['container'])
            for error in env['errors']:
                f.write('\n\t\t\tCOMMAND: %s\n\t\t\t\tERROR:%s' % (error.get('command', 'import' + error.get('import', 'nothing found')), error['output']))                
        f.write('\n\tNO TEST AVAILABLE:')
        for env in test_results['notest']:
            f.write('\n\t\t%s' % env)

if __name__ == '__main__':
    test()

    # import doctest
    # doctest.testmod()
