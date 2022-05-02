run_dir=$('pwd')
imgspec_dir=$(cd "$(dirname "$0")" ; pwd -P)
pge_dir=$(dirname ${imgspec_dir})

conda create -y --name sister python=3.7
source activate sister
conda install -y tensorflow
cd $pge_dir
python setup.py install
