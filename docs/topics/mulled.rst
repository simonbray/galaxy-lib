The Mulled Toolkit
========================

The mulled toolkit distributed as part of `galaxy-lib` allows for the automatic
generation and testing of containers from Conda_ packages. These containers can
be used stand alone on the command-line or automatically as part of properly
annotated Galaxy_ or CWL_ tools.

This documentation describes the low-level mulled toolkit, but for information
on using these containers automatically with tools check out these other documents:

- `Galaxy tool development with containers <http://planemo.readthedocs.io/en/latest/writing_advanced.html#dependencies-and-docker>`__
- `Using cwltool with Biocontainers <https://github.com/common-workflow-language/cwltool#leveraging-softwarerequirements-beta>`__

The mulled toolkit utilizes mulled_ with involucro_ in an automatic way to build
and test containers. This for example has been used to convert all packages in
bioconda_ into Linux Containers (Docker and rkt at the moment) and made available
via the `BioContainers Quay.io account`_.

Once you have `installed galaxy-lib
<http://galaxy-lib.readthedocs.io/en/latest/installation.html>`__,
several mulled utilities should be configured on your ``PATH`` including
``mulled-search``, ``mulled-build``, ``mulled-build-channel``, and
``mulled-build-tool``.

Some examples of using these tools are described below.

Search for containers
^^^^^^^^^^^^^^^^^^^^^

This will search for Docker containers (in the biocontainers organisation on quay.io), Singularity containers (located at https://depot.galaxyproject.org/singularity/), Conda packages (in the bioconda channel), and GitHub files (on the bioconda-recipes repository. 

.. code-block:: bash

   $ mulled-search --destination docker conda --search vsearch

The user can specify the location(s) for a search using the ``--destination`` option. The search term is specified using ``--search``. Multiple search terms can be specified simultaneously; in this case, the search will also encompass multi-package containers. For example, ``--search samtools bamtools``, will return ``mulled-v2-0560a8046fc82aa4338588eca29ff18edab2c5aa:c17ce694dd57ab0ac1a2b86bb214e65fedef760e-0``, in addition to all individual samtools and bamtools results.

If the user wishes to specify a quay.io organization or Conda channel for the search, this may be done using the ``--organization`` and ``--channel`` options respectively, e.g. ``--channel conda-forge``. Enabling ``--json`` causes results to be returned in JSON format.


Build all packages from bioconda from the last 24h
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The BioConda community is building a container for every package they create with a command similar to this.

.. code-block:: bash

   $ mulled-build-channel --channel bioconda --namespace biocontainers \
      --involucro-path ./involucro --recipes-dir ./bioconda-recipes --diff-hours 25 build

Building Docker containers for local Conda packages
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Conda packages can be tested with creating a busybox based container for this particular package in the following way.
This also demonstrates how you can build a container locally and on-the-fly.

  > we modified the samtools package to version 3.0 to make clear we are using a local version

1) build your recipe

.. code-block:: bash

   $ conda build recipes/samtools

2) index your local builds

.. code-block:: bash

   $ conda index /home/bag/miniconda3/conda-bld/linux-64/


3) build a container for your local package

.. code-block:: bash

   $ mulled-build build-and-test 'samtools=3.0--0' \
      -c iuc,conda-forge,bioconda,file://home/bag/miniconda3/conda-bld/ --test 'samtools --help'

The ``--0`` indicates the build version of the conda package. It is recommended to specify this number otherwise
you will override already existing images. For Python Conda packages this extension might look like this ``--py35_1``.

Build, test and push a conda-forge package to biocontainers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 > You need to have write access to the biocontainers repository

You can build packages from other Conda channels as well, not only from BioConda. ``pandoc`` is available from the
conda-forge channel and conda-forge is also enabled by default in Galaxy. To build ``pandoc`` and push it to biocontainrs
you could do something along these lines.

.. code-block:: bash

   $ mulled-build build-and-test 'pandoc=1.17.2--0' --test 'pandoc --help' -n biocontainers

.. code-block:: bash

   $ mulled-build push 'pandoc=1.17.2--0' --test 'pandoc --help' -n biocontainers

Build Singularity containers from Docker containers
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Singularity containers can be built from Docker containers using the mulled-update-singularity-containers command.

To generate a single container:

.. code-block:: bash

   $ mulled-update-singularity-containers --containers samtools:1.6--0 --logfile /tmp/sing/test.log --filepath /tmp/sing/ --installation /usr/local/bin/singularity

``--containers`` indicates the container name (here ``samtools:1.6--0``), ``--filepath`` the location where the containers should be placed, and ``--installation`` the location of the Singularity installation. (This can be found using ``whereis singularity``.)

Multiple containers can be installed simultaneously by giving ``--containers`` more than one argument:

.. code-block:: bash

   $ mulled-update-singularity-containers --containers samtools:1.6--0 bamtools:2.4.1--0 --filepath /tmp/sing/ --installation /usr/local/bin/singularity

.. code-block:: bash

For a large number of containers, it may be more convenient to employ the ``--container-list`` option:

.. code-block:: bash

   $ mulled-update-singularity-containers --container-list list.txt --filepath /tmp/sing/ --installation /usr/local/bin/singularity

Here ``list.txt`` should contain a list of containers, each on a new line.

In order to generate the list file the ``mulled-list`` command may be useful. The following command returns a list of all Docker containers available on the quay.io biocontainers organization, excluding those already available as Singularity containers via https://depot.galaxyproject.org/singularity/.:: bash

   $ mulled-list --source docker --not-singularity --blacklist blacklist.txt --file output.txt

The list of containers will be saved as ``output.txt``. The (optional) ``--blacklist`` option may be used to exclude containers which should not included in the output; ``blacklist.txt`` should contain a list of the 'blacklisted' containers, each on a new line.

Containers, once generated, should be tested. This can be achieved by affixing ``--testing test-output.log`` to the command, or alternatively, by use of the dedicated ``mulled-singularity-testing`` tool.:: bash

   $ mulled-singularity-testing --container-list list.txt --filepath /tmp/sing/ --installation /usr/local/bin/singularity --logfile test-output.txt

.. _Galaxy: https://galaxyproject.org/
.. _CWL: http://www.commonwl.org/
.. _mulled: https://github.com/mulled/mulled
.. _involucro: https://github.com/involucro/involucro
.. _Conda: https://conda.io/
.. _BioContainers: https://github.com/biocontainers
.. _bioconda: https://github.com/bioconda/bioconda-recipes
.. _galaxy-lib: https://github.com/galaxyproject/galaxy-lib
.. _BioContainers Quay.io account: https://quay.io/organization/biocontainers

Build, test and push containers to your own quay.io repository
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 > You need to have admin access to the quay.io organization or user.
 > If using travis and wish to encrypt your keys you will need to have the travis gem installed.

1) Generate the QUAY_OAUTH_TOKEN and add it to your .travis.yml

If you want your repositories to be public you must give involucro your
QUAY_OAUTH_TOKEN token. If you want private containers skip this step.

First head on over to your quay.io dashboard and create a new application for
the organization or user. This token will need to have permissions to create new
repositories. You can get the full instructions here <https://docs.quay.io/api/>
under the 'Applications and Tokens' heading. Once your key appears be sure to
store it someplace secure! I will say you are storing it in a plain text file
called ~/tokens/quay-oauth-token.

.. code-block:: bash

   $ cd my-recipes-repo
   ##Using Travis
   $ travis encrypt QUAY_OAUTH_TOKEN=`cat ~/tokens/quay-oauth-token`  --add
   ##Local Builds
   $ export QUAY_OAUTH_TOKEN=`cat ~/tokens/quay-oauth-token`


For more information on encrypting keys using travis see
<https://docs.travis-ci.com/user/encryption-keys/>

2) Give involucro your authentication info

Give Involucro a URL with your information.

https://MY_USER:MY_PASSWORD@quay.io/v1/\?email\=MY_EMAIL

The password can either be a plaintext password or the encrypted password. If
you need to check this run ``docker login quay.io`` with your credentials. Save
it to a plain text file called ~/tokens/involucro-auth .

.. code-block:: bash

   $ cd my-recipes-repo
   ##Using Travis
   $ travis encrypt INVOLUCRO_AUTH=`cat ~/tokens/involucro-auth`  --add
   ##Local Builds
   $ export INVOLUCRO_AUTH=`cat ~/tokens/involucro-auth`

You can also export these variables to your own environment and try it out.

.. code-block:: bash

   $ cd my-recipes-repo
   $ export INVOLUCRO_AUTH=`cat ~/tokens/involucro-auth`
   $ export QUAY_OAUTH_TOKEN=`cat ~/tokens/quay-oauth-token`
   $ mulled-build build-and-test 'pandoc=1.17.2--0' --test 'pandoc --help' -n MY_QUAY
   $ mulled-build push 'pandoc=1.17.2--0' --test 'pandoc --help' -n MY_QUAY
