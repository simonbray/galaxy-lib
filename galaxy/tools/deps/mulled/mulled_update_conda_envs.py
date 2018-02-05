#!/usr/bin/env python
from mulled_update_singularity_containers import get_quay_containers, get_test, mulled_get_test
import subprocess
#from mulled_build import check_output
from subprocess import check_output
import logging
from glob import glob
import argparse

ENVIRONMENT_LOCATION = "/home/ubuntu/condaenvs"

def get_conda_envs():
    """
    Gets list of already existing envs
    # >>> t = get_conda_envs()
    # >>> 'samtools:latest' in t
    True
    """

    return [n.split('__')[-1].replace('@', ':') for n in glob('%s/*' % ENVIRONMENT_LOCATION)]

def get_missing_envs(quay_list, conda_list, blacklist_file=None):
    """
    # >>> get_missing_envs(quay_list=['1', '2', '3', 'h--1', 'g--2', 'r'], conda_list=['3', '4', '5'], blacklist_file='blacklisttest.txt')
    # ['1', '2', 'h--1']
    """
    list_to_return = []
    blacklist = []
    if blacklist_file:
        blacklist = open(blacklist_file).read().split('\n')

    return [n for n in quay_list if n.split('--')[0] not in conda_list and n.split('--')[0] not in blacklist]


def extract_env_from_container(container): #container as name:build--version
    """
    Convert docker to singularity container
    # >>> from glob import glob
    # >>> glob('%s/__abundancebin@1.0.1--0' % ENVIRONMENT_LOCATION)
    # []
    # >>> extract_env_from_container('abundancebin:1.0.1--0')
    # >>> glob('%s/__abundancebin@1.0.1' % ENVIRONMENT_LOCATION)
    # ['/home/ubuntu/condaenvs/__abundancebin@1.0.1']
    """

    envname = '__%s' % '@'.join(container.split('--')[0].split(':'))
    try:
        check_output("cid=`docker run -d quay.io/biocontainers/%s` && sudo docker cp $cid:/usr/local/ %s/%s && docker stop $cid && docker rm $(docker ps -a -q) && docker rmi $(docker images -q)" % (container, ENVIRONMENT_LOCATION, envname), shell=True)
    except subprocess.CalledProcessError as e:
        error_info = {'code': e.returncode, 'cmd': e.cmd, 'out': e.output, 'container': container}
        return error_info
    else:
        return None

def test_conda_env(tests):
    """
    Run tests, record if they pass or fail
    >>> results = test_conda_env({'__samtools@latest': {'commands': ['samtools --help'], 'import_lang': 'python -c'}, '__pybigwig@0.1.11--py36_0': {'imports': ['pyBigWig'], 'commands': ['python -c "import pyBigWig; assert(pyBigWig.numpy == 1); assert(pyBigWig.remote == 1)"'], 'import_lang': 'python -c'}, '__yasm@1.3.0--0': {}})
    >>> 'pyBigWig' in results['failed'][0]['imports']
    True
    >>> '__samtools@latest' in results['passed']
    True
    >>> '__yasm@1.3.0--0' in results['notest']
    True

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
    parser.add_argument('-nt', '--no-testing', dest='no_testing', action="store_true",
                        help="Skip testing of generated environments (not recommended).")
    parser.add_argument('-b', '--blacklist', dest='blacklist', default=None, 
                        help="Provide a 'blacklist file' containing environments which should not be processed.")
    parser.add_argument('-o', '--logfile', dest='logfile', default='conda.log',
                        help="Filename for a log to be written to.")

    if not args.envs:
        envs = get_missing_envs(quay_list=get_quay_containers(), conda_list=get_conda_envs(), blacklist_file=args.blacklist)
    else:
        envs = args.containers

    with open(args.logfile, 'w') as f:
        f.write("SINGULARITY CONTAINERS GENERATED:")

        for env in envs:
            extract_env_from_container(env)

        if not args.no_testing:
            tests = {}
            for env in envs:
                if env[0:6] == 'mulled': # if it is a 'hashed container'
                    tests['__%s' % env.replace(':', '@')] = mulled_get_test(env)
                else:
                    tests[env] = get_test(env)
                
            test_results = test_conda_env(tests)
    
            f.write('\n\tTEST PASSED:')
            for env in test_results['passed']:
                f.write('\n\t\t%s' % env)
            f.write('\n\tTEST FAILED:')
            for env in test_results['failed']:
                f.write('\n\t\t%s' % env['env'])
                for error in env['errors']:
                    f.write('\n\t\t\tCOMMAND: %s\n\t\t\t\tERROR:%s' % (error.get('command', 'import' + error.get('import', 'nothing found')), error['output']))                
            f.write('\n\tNO TEST AVAILABLE:')
            for env in test_results['notest']:
                f.write('\n\t\t%s' % env)
        else:
            for env in envs:
                f.write('\n\t%s' % env)

if __name__ == '__main__':
    #main()

    import doctest
    doctest.testmod()