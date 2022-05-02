import argparse
import sys
from MDNPC import image_estimates
from MDNPC.parameters import get_args
from MDNPC.utils import set_kwargs_PC
import numpy as np
import hytools_lite as htl
from hytools_lite.io.envi import WriteENVI, envi_header_dict
from scipy.interpolate import interp1d

PRISMA_WAVES = [500, 507, 515, 523, 530,
				  538, 546, 554, 563, 571, 579, 588, 596, 605, 614, 623, 632, 641, 651, 660, 670, 679, 689,
				  699, 709, 719, ]


def main():
    ''' Estimate phycocyanin concentration from hyperspectral imagery.
    This function is a wrapper around phycocyanin MDN estimator from
    https://github.com/STREAM-RS/MDN-Phycocyanin

    O'Shea, R. E., Pahlevan, N., Smith, B., Bresciani,
    M., Egerton, T., Giardino, C., ... & Vaičiūtė, D. (2021).
    Advancing cyanobacteria biomass estimation from hyperspectral observations:
    Demonstrations with HICO and PRISMA imagery. Remote Sensing of Environment, 266, 112693.
    '''

    parser = argparse.ArgumentParser()
    parser.add_argument('rfl_file', type=str,
                        help='Input reflectance image')
    parser.add_argument('out_dir', type=str,
                          help='Output directory')
    args = parser.parse_args()

    out_dir = args.out_dir+'/' if not args.out_dir.endswith('/') else args.out_dir

    rfl = htl.HyTools()
    rfl.read_file(args.rfl_file,'envi')

    #Use NDVI as a water mask
    ndvi = rfl.ndi()

    #Clear system arguments, needed or else error thrown by MDN function
    sys.argv = [sys.argv[0]]
    sensor = "PRISMA-noBnoNIR"
    args2 = get_args(set_kwargs_PC(sensor))
    print(args2)

    pc = np.zeros((rfl.lines,rfl.columns,1))
    iterator =rfl.iterate(by = 'chunk',chunk_size = (500,500))
    while not iterator.complete:
        chunk = iterator.read_next()/np.pi
        water = (ndvi[iterator.current_line:iterator.current_line+chunk.shape[0],
                      iterator.current_column:iterator.current_column+chunk.shape[1]] < 0).sum()
        if water > 0:
            interper = interp1d(rfl.wavelengths,chunk)
            hico_chunk = interper(PRISMA_WAVES)
            output, idx = image_estimates(hico_chunk/np.pi,args=args2, sensor=sensor)
            pc[iterator.current_line:iterator.current_line+chunk.shape[0],
                iterator.current_column:iterator.current_column+chunk.shape[1],0] = output[idx['PC']][0]

    #Mask pixels outside of bounds
    pc[ndvi > 0.1] = -9999
    pc[~rfl.mask['no_data']] = -9999

    # Export phycocyanin map
    phyco_header =  envi_header_dict()
    phyco_header['header offset'] = 0
    phyco_header['data type'] = 4
    phyco_header['interleave'] ='bil'
    phyco_header['byte order'] = 0
    phyco_header['lines'] =rfl.lines
    phyco_header['samples'] =rfl.columns
    phyco_header['bands']= 1
    phyco_header['map info'] = rfl.get_header()['map info']
    phyco_header['description']= 'Phycocyanin content mg-m3'
    phyco_header['band names']= ['phycocyanin']
    phyco_header['data ignore value']= -9999

    out_file = "%s/%s_phyco" % (out_dir,rfl.base_name[:-3])
    writer = WriteENVI(out_file,phyco_header)
    writer.write_band(np.log(pc[:,:,0]),0)

if __name__ == "__main__":
    main()
