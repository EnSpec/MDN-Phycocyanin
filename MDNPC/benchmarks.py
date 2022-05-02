from .metrics          import performance
from .utils            import find_wavelength, ignore_warnings
from .meta             import get_sensor_bands
from .transformers     import TransformerPipeline, LogTransformer, RatioTransformer
from .Benchmarks.utils import get_benchmark_models, GlobalRandomManager

from collections import defaultdict as dd
from importlib   import import_module
from functools   import partial, update_wrapper
from pathlib     import Path 

import numpy as np
import pkgutil, warnings, traceback, sys, os

def get_methods(wavelengths, sensor, product, debug=True, allow_opt=False, **kwargs):
	''' Retrieve all benchmark functions from the appropriate product
		directory. Import each function with "model" in the function
		name, ensure any necessary parameters have a default value 
		available, and test whether the function can be run with the
		given wavelengths. A template folder for new algorithms is 
		available in the Benchmarks directory.
	'''
	models = get_benchmark_models(product, allow_opt, debug)
	print(models)
	sensor = sensor.split('-')[0]
	valid  = {}

	# Gather all models which return an output with the available wavelengths
	for name, model in models.items():
		sample_input = np.ones((1, len(wavelengths)))
		model_args   = [sample_input, wavelengths, sensor]
		model_kwargs = dict(kwargs)

		# Add a set of optimization dummy parameters to check if wavelengths are valid for the method
		if getattr(model, 'has_default', False):
			model_kwargs.update( dict(zip(model.opt_vars, [1]*len(model.opt_vars))) )

		try:
			assert(model(*model_args, **model_kwargs) is not None), 'Output is None'
			valid[name] = update_wrapper(partial(model, sensor=sensor), model)
		except Exception as e: 
			if debug: print(f'Exception for function {name}: {e}')		
	return valid


@ignore_warnings
def bench_product(sensor, X, y=None, bands=None, args=None, slices=None, silent=False, product='chl', method=None):	
	if bands is None:
		bands = get_sensor_bands(sensor, args)
	assert(X.shape[1] == len(bands)), f'Too many features given as bands for {sensor}: {X.shape[1]} vs {len(bands)}'

	if product in ['a', 'aph', 'ap', 'ag', 'aph', 'adg', 'b', 'bbp']:
		from .Benchmarks.multiple.QAA.model import model as QAA
		methods = {'QAA': lambda *args, **kwargs: QAA(*args)[product]}
	else:
		methods = get_methods(bands, sensor, product, tol=15)
	assert(method is None or method in methods), f'Unknown algorithm "{method}". Options are: \n{list(methods.keys())}'

	ests = []
	lbls = []
	print('Method Items')
	print(methods.items())
	for name, func in methods.items():
		if method is None or name == method:
			if name == 'GIOP':
				continue

			est_val = func(X, bands, tol=15,b_b_742=args)

			if product == 'chl' or product == 'phycocyanin' or product == 'aph' or product == 'adg' or product == 'b':
				est_val[est_val < 0] = np.nan


			if not silent and y is not None:
				curr_slice = slices
				if slices is None:
					assert(y.shape[1] == est_val.shape[1]), 'Ambiguous y data provided - need to give slices parameter.'
					curr_slice = {product:slice(None)}

				ins_val = y[:, curr_slice[product]]
				for i in range(ins_val.shape[1]):
					performance_text = performance(name, ins_val[:, i], est_val)
					print( performance_text )

			ests.append(est_val)
			lbls.append(name)


	return dict(zip(lbls, ests))


def get_models(wavelengths, sensor, product, debug=False, allow_opt=False, method=None, **kwargs):
	''' Retrieve all benchmark functions from the appropriate product
		directory. Import each function with "model" in the function
		name, ensure any necessary parameters have a default value 
		available, and test whether the function can be run with the
		given wavelengths. A template folder for new algorithms is 
		available in the Benchmarks directory.
	'''
	valid  = {}
	sensor = sensor.split('-')[0] 
	models = get_benchmark_models(product, allow_opt, debug, method)
	kwargs.update({
		'sensor'      : sensor, 
		'wavelengths' : wavelengths, 
		'product'     : product,
		'allow_opt'   : allow_opt,
	})

	# Gather all models which return an output with the available wavelengths
	for name, model in models.items():
		sample_input = np.ones((1, len(wavelengths)))
		model_kwargs = dict(kwargs)

		# Add a set of optimization dummy parameters to check if wavelengths are valid for the method
		if getattr(model, 'has_default', False):
			model_kwargs.update( dict(zip(model.opt_vars, [1]*len(model.opt_vars))) )

		try:
			output = model(sample_input, **model_kwargs)
			assert(output is not None), f'Output for {name} is None'
			assert(not isinstance(output, dict)), f'"{product}" not found in the outputs of {name}'
			valid[name] = update_wrapper(partial(model, **kwargs), model)
		except Exception as e: 
			if debug: print(f'Exception for function {name}: {e}\n{traceback.format_exc()}')		
	return valid


@ignore_warnings
def run_benchmarks(sensor, x_test, y_test=None, x_train=None, y_train=None, slices=None, args=None, 
					*, product='chl', bands=None, verbose=False, 
					return_rs=True, return_ml=False, return_opt=False,
					kwargs_rs={},   kwargs_ml={},    kwargs_opt={}):
	''' Run all available benchmark algorithms on the given data. 
		- return_rs : Include remote sensing (domain) algorithms in the returned dictionary
		- return_ml : Include machine learning algorithms in the returned dictionary (must
		              pass x_train, y_train variables to the function)
		- return_opt: Include remote sensing (domain) algorithms that allow for optimization
		              in the returned dictionary (must pass x_train, y_train variables)

		The returned object is a nested dictionary with format:
			{product: {algorithm: estimates, ...}, ...}
	'''
	def assert_same_features(a, b, label):
		assert(a is None or b is None or a.shape[1] == b.shape[1]), \
			f'Differing number of {label} features: {a.shape[1]} vs {b.shape[1]}'

	slices = slices or {product: slice(None)}
	bands  = np.array(get_sensor_bands(sensor, args) if bands is None else bands)
	bench  = dd(dict)

	# Ensure training / testing data have the same number of features, and the appropriate number of bands
	assert_same_features(x_test, x_train, 'x')
	assert_same_features(y_test, y_train, 'y')
	assert_same_features(x_test, np.atleast_2d(bands), f'{sensor} band')
	
	if (return_ml or return_opt) and (x_train is None or y_train is None):
		raise Exception('Training data must be passed to use ML/Opt models')

	# Set the avaliable products for each set of benchmarking methods
	products_rs  = ['chl', 'tss', 'cdom', 'a', 'aph', 'ap', 'ag', 'aph', 'adg', 'b', 'bbp', 'PC']
	products_ml  = ['chl', 'tss', 'cdom', 'PC']
	products_opt = ['chl', 'tss', 'cdom', 'PC'] 

	# Get the benchmark estimates for each product individually
	for product in slices:

		kwargs_default = {
			'bands'   : bands,
			'args'    : args,
			'sensor'  : sensor, 
			'product' : product,
			'verbose' : verbose,
			'x_train' : x_train,
			'x_test'  : x_test,
			'y_train' : y_train[:, slices[product]] if y_train is not None else None,
			'y_test'  :  y_test[:, slices[product]] if y_test  is not None else None,
		}

		for bench_return, bench_products, bench_kwargs, bench_function in [
			(return_rs,  products_rs,  dict(kwargs_rs ),  _bench_rs ),
			(return_ml,  products_ml,  dict(kwargs_ml ),  _bench_ml ),
			(return_opt, products_opt, dict(kwargs_opt),  _bench_opt),
		]:
			if bench_return and product in bench_products:
				bench_kwargs.update(kwargs_default)
				bench[product].update( bench_function(**bench_kwargs) )
	return dict(bench)


def _create_estimates(model, inputs, postprocess=None, preprocess=None, **kwargs): 
	if postprocess is None: postprocess = lambda x: x
	if preprocess  is None: preprocess  = lambda x: x
	print(model.__name__)

	model     = model 
	outputs   = getattr(model, 'predict', model)(inputs.copy())
	estimates = postprocess(outputs.flatten()[:, None])

	if kwargs.get('verbose', False) and kwargs.get('y_test', None) is not None:
		performance_text = performance(model.__name__, kwargs['y_test'], estimates)
		print( performance_text )
		performance_file = open('/home/ryanoshea/MDN_PC/MDN/scatter_plots/performance_file.txt','a')
		performance_file.write(performance_text+'\n')
		performance_file.close()
	return estimates


def _bench_rs(sensor, bands, x_test, product='chl', method=None, tol=5, allow_opt=False, **kwargs):
	postps = lambda x: (np.copyto(x, np.nan, where=x < 0) or x) if product == 'chl' else x 
	create = lambda f: _create_estimates(f, x_test, postps, **kwargs)
	models = get_models(bands, sensor, product, method=method, tol=tol, allow_opt=allow_opt,**kwargs)
	return {name: create(model) for name, model in models.items()}
	

def _bench_opt(sensor, bands, x_train, y_train, *args, **kwargs):
	performance_file = open('/home/ryanoshea/MDN_PC/MDN/scatter_plots/performance_file.txt','a')
	performance_file.write('OPTIMIZED MODELS \n')
	performance_file.close()
	preproc = lambda m: m.fit(x_train, y_train, bands)

	kwargs['x_train'] = x_train
	kwargs['y_train'] = y_train

	#print(kwargs.get('bands'))
	estims  = _bench_rs(sensor, bands, *args, allow_opt=True, preprocess=1, **kwargs)
	return {f'{k}_opt': v for k, v in estims.items()}


def _bench_ml(sensor, x_train, y_train, x_test, *, x_other=None, verbose=False,
			seed=42, bagging=True, gridsearch=False, scale=True, **kwargs):

	from sklearn.preprocessing import RobustScaler, MinMaxScaler
	from sklearn.model_selection import GridSearchCV
	from sklearn.ensemble import BaggingRegressor
	from .Benchmarks.ML import models 

	seed = getattr(getattr(kwargs, 'args', None), 'seed', seed)
	gridsearch_kwargs = {'refit': False, 'scoring': 'neg_median_absolute_error'}
	bagging_kwargs    = {
		'n_estimators' : 10,
		'max_samples'  : 0.75,
		'bootstrap'    : False,
		'random_state' : seed,
	}

	if scale:
		x_scaler = TransformerPipeline([RobustScaler()])
		y_scaler = TransformerPipeline([LogTransformer(), MinMaxScaler((-1, 1))]) 
		x_scaler.fit(x_train)
		y_scaler.fit(y_train)
		x_test  = x_scaler.transform(x_test)
		x_train = x_scaler.transform(x_train)
		y_train = y_scaler.transform(y_train).flatten()

	preprocess  = lambda m: m.fit(x_train.copy(), y_train.copy())
	postprocess = None if not scale else y_scaler.inverse_transform

	if verbose and gridsearch:
		print('\nPerforming gridsearch...')

	other = {}
	estim = {}
	for method, params in models.items():
		params['grid']['random_state'] = params['default']['random_state'] = seed
		model_kwargs = params['default']

		with GlobalRandomManager(seed):
			if gridsearch and method != 'SVM':
				model = GridSearchCV(params['class'](), params['grid'], n_jobs=3 if method != 'MDN' else 1, **gridsearch_kwargs)
				model.fit(x_train.copy(), y_train.copy())

				model_kwargs = model.best_params_
				if verbose: print(f'Best {method} params: {model_kwargs}')

			model = params['class'](**model_kwargs)
			if bagging: model = BaggingRegressor(model, **bagging_kwargs)

			model.__name__ = method
			estim[method]  = _create_estimates(model, x_test, postprocess, preprocess, verbose=verbose, **kwargs)
			
			if x_other is not None:
				other[method] = _create_estimates(model, x_other, postprocess)

	if len(other):
		return estim, other
	return estim
