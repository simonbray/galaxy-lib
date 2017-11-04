#!/usr/bin/env python

import argparse
import json
import sys
import tempfile
import urllib2
import logging

#import subprocess
import conda_api

try:
    import requests
except ImportError:
    requests = None

from util import build_target, v2_image_name

try:
    from whoosh.fields import Schema
    from whoosh.fields import TEXT
    from whoosh.fields import STORED
    from whoosh.index import create_in
    from whoosh.qparser import QueryParser
except ImportError:
    Schema = TEXT = STORED = create_in = QueryParser = None

QUAY_API_URL = 'https://quay.io/api/v1/repository'

class QuaySearch():
    """
    Tool to search within a quay organization for a given software name.

    >>> t = QuaySearch("biocontainers")
    >>> t.build_index()
    >>> t.search_repository("adsfasdf", True)
    []
    >>> t.search_repository("adsfasdf", False)
    []
    >>> {'version': u'2.2.0--0', 'package': u'bioconductor-gosemsim'} in t.search_repository("bioconductor-gosemsim", True) 
    True
    """

    def __init__(self, organization):
        self.index = None
        self.organization = organization

    def build_index(self):
        """
        Create an index to quickly examine the repositories of a given quay.io organization.
        """
        # download all information about the repositories from the
        # given organization in self.organization

        parameters = {'public': 'true', 'namespace': self.organization}
        r = requests.get(QUAY_API_URL, headers={'Accept-encoding': 'gzip'}, params=parameters, timeout=12)
        tmp_dir = tempfile.mkdtemp()
        schema = Schema(title=TEXT(stored=True), content=STORED)
        self.index = create_in(tmp_dir, schema)

        json_decoder = json.JSONDecoder()
        decoded_request = json_decoder.decode(r.text)
        writer = self.index.writer()
        for repository in decoded_request['repositories']:
            writer.add_document(title=repository['name'], content=repository['description'])
        writer.commit()

    def search_repository(self, search_string, non_strict):
        """
        Search Docker containers on quay.io.
        Results are displayed with all available versions,
        including the complete image name.
        
        """
        # with statement closes searcher after usage.
        with self.index.searcher() as searcher:
            #search_string = "*%s*" % search_string
            query = QueryParser("title", self.index.schema).parse(search_string)
            results = searcher.search(query)
            if non_strict:
                # look for spelling errors and use suggestions as a search term too
                corrector = searcher.corrector("title")
                suggestions = corrector.suggest(search_string, limit=2)

                # get all repositories with suggested keywords
                for suggestion in suggestions:
                    search_string = "*%s*" % suggestion
                    query = QueryParser("title", self.index.schema).parse(search_string)
                    results_tmp = searcher.search(query)
                    results.extend(results_tmp)

            out = list()

            for result in results:
                title = result['title']
                for version in self.get_additional_repository_information(title):
                    try:
                        version, build = version.split('--')
                    except ValueError:
                        version, build = version, None
                    out.append({'package': title, 'version': version, 'build': build})

            return out


            # sys.stdout.write("The query \033[1m %s \033[0m resulted in %s Docker result(s) with %s available version(s).\n" % (search_string, len(results), len(out)))

            # if non_strict:
            #     sys.stdout.write('The search was relaxed and the following search terms were searched: ')
            #     sys.stdout.write('\033[1m %s \033[0m\n' % ', '.join(suggestions))

            # if out:
            #     col_width = max(len(word) for row in out for word in row) + 2  # padding
            #     for row in out:
            #         name = row[0]
            #         version = row[1]
            #         sys.stdout.write("".join(word.ljust(col_width) for word in row) + "docker pull quay.io/%s/%s:%s\n" % (self.organization, name, version))
            # else:
            #     sys.stdout.write("No results found for %s in quay.io/%s.\n" % (search_string, self.organization))

            

    def get_additional_repository_information(self, repository_string):
        """
        Function downloads additional information from quay.io to
        get the tag-field which includes the version number.

        

        """
        url = "%s/%s/%s" % (QUAY_API_URL, self.organization, repository_string)
        r = requests.get(url, headers={'Accept-encoding': 'gzip'})

        json_decoder = json.JSONDecoder()
        decoded_request = json_decoder.decode(r.text)
        return decoded_request['tags']


class CondaSearch():
    """
    Tool to search the bioconda channel


    >>> t = CondaSearch()
    
    >>> t.process_json(t.get_json("adsfasdf"), "adsfasdf")
    []
    >>> {'version': u'2.2.0', 'build': u'0', 'package': u'bioconductor-gosemsim'} in t.process_json(t.get_json("bioconductor-gosemsim"), "bioconductor-gosemsim") 
    True


    """

    def get_json(self, search_string):
        """
        Function takes search_string variable and returns results from the bioconda channel in JSON format 

        """
        conda_api.set_root_prefix()
        json_output = conda_api.search(search_string)

        return json_output

    def process_json(self, json_input, search_string):
        """
        Function takes JSON input and processes it, returning the required data
        """
        results = []
        #no_of_packages = 0
        #no_of_versions = 0

        try:
            json_input['exception_name'] # if the search fails, probably because there are no results
            return results
        except KeyError:
            pass

        for package_name, package_info in json_input.iteritems():
            #no_of_packages += 1
            for item in package_info:
                build = item['build']
                version = item['version']
                if (package_name, build, version) not in results: # don't duplicate results
                    results.append({'package': package_name, 'build': build, 'version': version})
                    #no_of_versions += 1
        return results

    # def print_output(json_input):

    #     col_width = 30
    #     col_width = max(len(word) for result in results for word in result) + 2  # padding

    #     sys.stdout.write("\nThe query \033[1m %s \033[0m resulted in %s bioconda result(s) with %s available version(s).\n" % (search_string, no_of_packages, no_of_versions))

    #     for result in results:
    #         sys.stdout.write("".join([result[0].ljust(col_width), (result[2] + "--" + result[1]).ljust(col_width)]) + "conda install -c bioconda %s=%s\n" % (result[0], result[2]))
            

    # def search(self, search_string):
    #     conda_output = subprocess.Popen("conda search %s -c bioconda" % (search_string), shell=True, stdout=subprocess.PIPE)
        
    #     try:
    #         lines = []
    #         for line in conda_output:
    #             #sys.stdout.write(line)
    #             lst = line.split()
    #             del lst[-1]
    #             lines.append(lst)
    #         del lines[0]

        #     results = 0   
            # for line in lines:
        #         #package = None
        #         try:
        #             int(line[0][0])
        #             line.insert(0, package)
        #         except ValueError:
        #             package = line[0]
        #             results += 1
        #     col_width = max(len(word) for row in lines for word in row) + 2  # padding

        #     sys.stdout.write("\nThe query \033[1m %s \033[0m resulted in %s bioconda result(s) with %s available version(s).\n" % (search_string, results, len(lines)))

        #     for line in lines:
        #         sys.stdout.write("".join([line[0].ljust(col_width), (line[1] + "--" + line[2]).ljust(col_width)]) + "conda install -c bioconda %s=%s\n" % (line[0], line[1]))
        
        # except ValueError:
        #     sys.stdout.write("No conda packages were found matching '%s'.\n" % search_string)

class GitHubSearch():
    """
    Tool to search the GitHub bioconda-recipes repo


    >>> t = GitHubSearch()
    >>> t.process_json(t.get_json("adsfasdf"), "adsfasdf")
    []
    >>> t.process_json(t.get_json("bamtool"), "bamtool")
    []
    >>> {'path': u'recipes/bioconductor-gosemsim/build.sh', 'name': u'build.sh'} in t.process_json(t.get_json("bioconductor-gosemsim"), "bioconductor-gosemsim") 
    True

        
    """

    #def __init__(self, organization):
    #    self.organization = organization

    def get_json(self, search_string):
        """
        Function takes search_string variable and returns results from the bioconda-recipes github repository in JSON format 
        """
        response = json.loads(urllib2.urlopen("https://api.github.com/search/code?q=%s+in:path+repo:bioconda/bioconda-recipes+path:recipes" % search_string).read())
        return response

    def process_json(self, json, search_string):
        """
        Function takes JSON input and processes it, returning the required data
        """

        json = json['items'][0:10] #get top ten results
        
        results = []
        for result in json:
            results.append({'name': result['name'], 'path': result['path']})
        return results

        # print "Here are the best matches for the query provided."    
        
        # col_width = max(len(result['name']) for result in json) + 2  # padding
        # for result in json:
        #     sys.stdout.write("".join([result['name'].ljust(col_width), "https://github.com/bioconda/bioconda-recipes/tree/master/" + result['path'] + "\n"]))
    
    def recipe_present(self, search_string):
        """
        Checks if a recipe exists in bioconda-recipes which matches search_string exactly
        
        >>> t = GitHubSearch()
        >>> t.recipe_present("bioconductor-gosemsim")
        True

        >>> t.recipe_present("bioconductor-gosemsi")
        False

        >>> t.recipe_present("bioconductor_gosemsim")
        False

        """
        try:
            json.loads(urllib2.urlopen("https://api.github.com/repos/bioconda/bioconda-recipes/contents/recipes/%s" % search_string).read())
            recipe_present = True
        except urllib2.HTTPError:
            recipe_present = False

        #if recipe_present:
        #    print "A recipe named %s is present in the GitHub repository at the following URL:" % search_string
        #    print "https://github.com/bioconda/bioconda-recipes/tree/master/recipes/%s" % search_string

        #else:
        #    print "No recipe with the name %s could be found." % search_string

        return recipe_present

def get_package_hash(packages, versions):
    """
    Takes packages and versions (if the latter are given) and returns a hash for each. Also checks github to see if the container is already present.
    
    >>> get_package_hash(['bamtools', 'samtools'], {})
    {'container_present': True, 'package_hash': 'mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa'}
    >>> get_package_hash(['bamtools', 'samtools'], {'bamtools':'2.4.0', 'samtools':'1.3.1'})
    {'container_present': True, 'version_hash': 'c17ce694dd57ab0ac1a2b86bb214e65fedef760e', 'container_present_with_version': True, 'package_hash': 'mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa'}
    >>> get_package_hash(['abricate', 'abyss'], {'abricate': '0.4', 'abyss': '2.0.1'})
    {'container_present': False, 'version_hash': 'e21d1262f064e1e01b6b9fad5bea117928f31b38', 'package_hash': 'mulled-v2-cde36934a4704f448af44bf01deeae8d2832ca2e'}
    
    """

    hash_results = {}
    targets = []
    if versions: 
        for p in packages:
            targets.append(build_target(p, version=versions[p]))
    else: #if versions are not given only calculate the package hash
        for p in packages:
            targets.append(build_target(p))
    package_hash = v2_image_name(targets) #make the hash from the processed targets
    hash_results['package_hash'] = package_hash.split(':')[0]
    if versions:
        hash_results['version_hash'] = package_hash.split(':')[1]
    try:
        r = json.loads(urllib2.urlopen("https://quay.io/api/v1/repository/biocontainers/%s" % hash_results['package_hash']).read())
    except urllib2.HTTPError:
        hash_results['container_present'] = False # page could not be retrieved so container not present
    else:
        hash_results['container_present'] = True
        if versions: # now test if the version hash is listed in the repository tags
            tags = [n[:-2] for n in r['tags']] #remove -0, -1, etc from end of the tag
            if hash_results['version_hash'] in tags:
                hash_results['container_present_with_version'] = True
            else:
                hash_results['container_present_with_version'] = False

    return hash_results

def singularity_search(hash_dict):
    """
    Checks if a singularity package is present at the galaxy website and returns the link.
    >>> singularity_search({'container_present': True, 'version_hash': 'c17ce694dd57ab0ac1a2b86bb214e65fedef760e', 'package_hash': 'mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa'})
    'mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa%3Ac17ce694dd57ab0ac1a2b86bb214e65fedef760e-0'
    >>> singularity_search({'container_present': False, 'version_hash': 'cb5455068b161c76257d2e2bcffa58f54f920291', 'package_hash': 'mulled-v2-19fa9431f5863b2be81ff13791f1b00160ed0852'}) is None
    True
    """

    full_hash = "%3A".join([hash_dict['package_hash'], hash_dict['version_hash']])
    #remove initial and final lines from html with [4:-3] slice then extract hash with split('"'). Dictionary consists of {hash: url}.
    urls = {n.split('"')[1][:-2]: n.split('"')[1] for n in urllib2.urlopen("https://depot.galaxyproject.org/singularity/").read().split("\n")[4:-3]}
    return urls.get(full_hash) # returns the url if present, otherwise None

def main(argv=None):
    if Schema == None:
        sys.stdout.write("Required dependencies are not installed. Run 'pip install Whoosh'.\n")
        return

    parser = argparse.ArgumentParser(description='Searches in a given quay organization for a repository')
    parser.add_argument('-d', '--destination', dest='search_dest', nargs='+', default=['quay', 'conda'],
                        help="Choose where to search. Options are 'conda' and 'quay'. If no option are given, all will be searched.")
    parser.add_argument('-o', '--organization', dest='organization_string', default="biocontainers",
                        help='Change quay organization. Default is biocontainers.')
    parser.add_argument('--non-strict', dest='non_strict', action="store_true",
                        help='Autocorrection of typos activated. Lists more results but can be confusing.\
                        For too many queries quay.io blocks the request and the results can be incomplete.')
    parser.add_argument('--json', dest='json', action="store_true", help='Returns results as JSON.')
    parser.add_argument('-s', '--search', required=True, nargs='+',
                        help='The name of the tool you want to search for.')
    parser.add_argument('-v', '--version', dest='version', action="store_true", help="Filter results by version numbers, which must be given with the package names.")

    args = parser.parse_args()

    json_results = {dest: None for dest in args.search_dest}

    versions = {}
    if args.version: # extract the version numbers from args.search_dest
        try:
            versions = {n.split('=')[0]: n.split('=')[1] for n in args.search}
            args.search = [n.split('=')[0] for n in args.search]
        except IndexError:
            logging.error("Please include a version number for every package you wish to search. Alternatively, remove the --version tag.")
            return

    if 'conda' in args.search_dest:
        conda_results = {}
        conda = CondaSearch()

        for item in args.search:
            conda_json = conda.get_json(item)
            conda_results[item] = conda.process_json(conda_json, item)
        json_results['conda'] = conda_results

    if 'github' in args.search_dest:
        github_results = {}
        github = GitHubSearch()

        for item in args.search:
            github_json = github.get_json(item)
            json_results['github'] = github.process_json(github_json, item)

    # if 'other' in args.search_dest:
        # implement other options

    if len(args.search) > 1: # get hash if multiple packages are searched
        json_results['hash'] = get_package_hash(args.search, versions)

    if 'quay' in args.search_dest:
        quay_results = {}
        quay = QuaySearch(args.organization_string)
        quay.build_index()

        for item in args.search:
            quay_results[item] = quay.search_repository(item, args.non_strict)
            
        if args.version: # if the version tag is on, filter by version
            for p in args.search:
                quay_results[p] = [q for q in quay_results[p] if q['version'] == versions[p]]

        json_results['quay'] = quay_results

    if 'singularity' in args.search_dest:
        if 'hash' in json_results:
            json_results['singularity'] = singularity_search(json_results['hash'])
        else:
            print("No hash available, probably because only one package was searched.")

    if args.json:
        # return format as json.
        print(json_results)
    else:
        # pretty formatting stuff here
        print("Not yet implemented.")

if __name__ == "__main__":
    main()

    #import doctest
    #doctest.testmod()