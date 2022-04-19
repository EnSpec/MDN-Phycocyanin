imgspec_dir=$(cd "$(dirname "$0")" ; pwd -P)
pge_dir=$(dirname ${imgspec_dir})

mkdir output
tar_file=$(ls input/*tar.gz)
#echo $tar_file
base=$(basename $tar_file)
#echo $base
scene_id=${base%.tar.gz}

if  [[ $scene_id == "ang"* ]]; then
    out_dir=$(echo $scene_id | cut -c1-18)_phyco
elif [[ $scene_id == "PRS"* ]]; then
    out_dir=$(echo $scene_id | cut -c1-38)_phyco
elif [[ $scene_id == "f"* ]]; then
    out_dir=$(echo $scene_id | cut -c1-16)_phyco
fi

yes | python ${pge_dir}/setup.py install

tar -xzvf $tar_file -C input

for a in `python ${imgspec_dir}/get_paths_from_granules.py`;
   do
       python ${pge_dir}/run_mdn.py $a output/$out_dir;
  done

cd output
tar -czvf $out_dir.tar.gz $out_dir
rm -r $out_dir
