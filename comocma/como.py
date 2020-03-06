#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module contains the implementation of the Sofomore algorithm in 2 objectives, defined in 
the paper [Toure, Cheikh, et al. "Uncrowded Hypervolume Improvement: 
        COMO-CMA-ES and the Sofomore framework." 
        GECCO'19-Genetic and Evolutionary Computation Conference. 2019.].
"""

from __future__ import division, print_function, unicode_literals
__author__ = "Cheikh Toure and Nikolaus Hansen"
__license__ = "BSD 3-clause"
__version__ = "0.5.0"
del division, print_function, unicode_literals

import numpy as np
import cma
from cma import interfaces
from nondominatedarchive import NonDominatedList
from moarchiving import BiobjectiveNondominatedSortedList
import warnings
import cma.utilities.utils
import os
from sofomore_logger import SofomoreDataLogger
#import sys

class Sofomore(interfaces.OOOptimizer):
    """ 
    Sofomore framework for multiobjective optimization, with the 
    ask-and-tell interface.
    See: [Toure, Cheikh, et al. "Uncrowded Hypervolume Improvement: 
        COMO-CMA-ES and the Sofomore framework." 
        GECCO'19-Genetic and Evolutionary Computation Conference. 2019.].
        
    Calling Sequences
    =================

    - ``moes = Sofomore(list_of_solvers_instances, opts, reference_point)``

    - ``moes = Sofomore(list_of_solvers_instances, reference_point)``

    - ``moes = Sofomore(list_of_solvers_instances, 
                             reference_point).optimize(objective_fcts)``

    Arguments   
    =========
    `list_of_solvers_instances`
        list of instances of single-objective solvers.
        It's generally created via a factory function.
        Let's take the example of a factory function that returns cma-es 
        instances, called `get_cmas`. Then:
        ``list_of_solvers_instances = get_cmas(11 * [x0], sigma0)`` 
        creates a list of 11 cma-es instances of initial mean `x0` and initial 
        step-size `sigma0`.
        A single-objective solver instance must have the following
        attributes and methods:
            - `incumbent`: an attribute that gives an estimate of 
            the single-objective solver.
            - `objective_values`: an attribute that stores the objective 
            values of the incumbent.
            - `stop`: a method returning a dictionary representing the 
            termination status.
            - `ask`: generates new candidate solutions.
            - `tell`: passes the objective values and updates the states of the
            single-objective solvers.
                
            
    `opts`
        opts, a dictionary with optional settings related to the 
        Sofomore framework. It contains the following keys:
            - 'archive': default value is `True`. 
            If its value is `True`, tracks the non-dominated
            points among the points evaluated so far during the 
            optimization.
            The archive will not interfere with the optimization 
            process.
            - 'update_order': default value is a function that takes a natural 
            integer as input and return a random number between 0 and 1.
            It is used as a `key value` in: `sorted(..., key = ...)`, and guides the
            order in which the kernels will be updated during the optimization.
 

    `reference_point`  
        reference point of the multiobjective optimization.
        Its default value is `None` but should be set by the user 
        beforehand to guarantee an optimal p-distribution convergence of 
        the Hypervolume indicator of `p` points towards the Pareto set/front.
        It can be changed dynamically by the user if needed.
        

    Main interface / usage
    ======================
    The interface is inherited from the generic `OOOptimizer`
    class, which is the same interface used by the python cma. An object 
    instance is generated as following:
        
        list_of_solvers_instances = como.get_cmas(11 * [x0], sigma0)
        moes = como.Sofomore(list_of_solvers_instances,
                             opts = opts,
                           reference_point = reference_point)

    The least verbose interface is via the optimize method::

         moes.optimize(objective_func)
         where `objective_func` is a callable multiobjective function

    More verbosely, the optimization of the multiobjective function 
    `objective_funcs` is done using the methods `stop`, `ask`, and `tell`::
        
        while not moes.stop():
            solutions = moes.ask()
            objective_values = [objective_funcs(x) for x in solutions]
            moes.tell(solutions, objective_values)
            moes.disp()

    where `ask` delivers new candidate solutions and `tell` updates
    the `optim` instance by passing the respective function values.

    Attributes and Properties
    =========================
    - `kernels`: initialized with `list_of_solvers_instances`, 
    and is the list of single-objective solvers.
    - `num_kernels`: length of `self.kernels`.
    - `opts`: passed options.
    - `pareto_front`: list of non-dominated points among the incumbents of 
    `self.kernels`.
    - `archive`: list of non-dominated points among all points evaluated 
    so far.
    - `reference_point`: the current reference point.
    - `offspring`: list of tuples of the index of a kernel with its 
    corresponding candidate solutions, that we generally get with the cma's 
    `ask` method.
    - _told_indices: the kernels' indices for which we will evaluate the 
    objective values of their incumbents, in the next call of the `tell` 
    method.
    Before the first call of `tell`, they are the indices of all the initial
    kernels (i.e. `range(self.num_kernels)`). And before another call of 
    `tell`, they are the indices of the kernels from which we have sampled new 
    candidate solutions during the penultimate `ask` method. 
    Note that we should call the `ask` method before any call of the `tell`
    method.
    - `key_sort_indices`: default value is `self.opts['update_order']`.
    It is a function used as a key to sort some kernels' indices, in order to
    select the first indices during the call of the `ask` method.
    """   
    def __init__(self,
               list_of_solvers_instances, # usually come from a factory function 
                                         #  creating single solvers' instances
               opts = None, # keeping an archive, decide whether we use restart, etc.
               reference_point = None,    
               ):
        """
        Initialization:
            - `list_of_solvers_instances` is a list of single-objective 
            solvers' instances
            - `opts` is a dictionary updating the values of 
            `archive` and `update_order`, that responds respectfully to whether
            or not tracking an archive, and the order of update of the kernels.
            - The reference_point is set by the user during the 
            initialization.
        """
        assert len(list_of_solvers_instances) > 0
        self.kernels = list_of_solvers_instances
        self.num_kernels = len(self.kernels)
        self.dimension = self.kernels[0].N
        self._active_indices = list(range(self.num_kernels))

        for kernel in self.kernels:
            if not hasattr(kernel, 'objective_values'):
                kernel.objective_values = None
        self.reference_point = reference_point
        defopts = {'archive': True, 'restart': None, 'verb_filenameprefix': 'outsofomore' + os.sep, 
                   'verb_log': 1, 'verb_disp': 100, 'update_order': sort_random}
        if opts is None:
            opts = {}
        if isinstance(opts, dict):
            defopts.update(opts)
        else:
            warnings.warn("options should be either a dictionary or None.")
        self.opts = defopts
        self.restart = self.opts['restart']
        self.isarchive = self.opts['archive']
        if self.isarchive:
            self.archive = []
        self.NDA = None # the method for nondominated archiving
        self.offspring = []
        self._told_indices = range(self.num_kernels)
        
        self.key_sort_indices = self.opts['update_order']
        self.countiter = 0
        self.countevals = 0
        self._remaining_indices_to_ask = range(self.num_kernels) # where we look when calling `ask`
        self.logger = SofomoreDataLogger(self.opts['verb_filenameprefix'],
                                                     modulo=self.opts['verb_log']).register(self)
        self.best_hypervolume_pareto_front = 0.0
        self.epsilon_hypervolume_pareto_front = 0.1 # the minimum positive convergence gap
                
        self._ratio_nondom_offspring_incumbent = self.num_kernels * [0]
    def __iter__(self):
        """
        make `self` iterable. 
        """
        return iter(self.kernels)
    
    def __getitem__(self, i):
        """
        make `self` subscriptable.
        """
        return self.kernels[i]
    
    def ask(self, number_to_ask = 1):
        """
        get the kernels' incumbents to be evaluated and sample new candidate solutions from 
        `number_to_ask` kernels.
        The sampling is done by calling the `ask` method of the
        `cma.CMAEvolutionStrategy` class.
        The indices of the considered kernels' incumbents are given by the 
        `_told_indices` attribute.
        
        To get the `number_to_ask` kernels, we use the function `self.key_sort_indices` as
        a key to sort `self._remaining_indices_to_ask` (which is the list of
        kernels' indices wherein we choose the first `number_to_ask` elements.
        And if `number_to_ask` is larger than `len(self._remaining_indices_to_ask)`,
        we select the list `self._remaining_indices_to_ask` extended with the  
        first `number_to_ask - len(self._remaining_indices_to_ask)` elements
        of `range(self.num_kernels)`, sorted with `self.key_sort_indices` as key.

        Arguments
        ---------
        - `number_to_ask`: the number of kernels where we sample solutions
         from, it's of type int and is smaller or equal to `self.num_kernels`
        
        Return
        ------
        The list of the kernels' incumbents to be evaluated, extended with a
        list of N-dimensional (N is the dimension of the search space) 
        candidate solutions generated from `number_to_ask` kernels 
        to be evaluated.
    
        :See: the `ask` method from the class `cma.CMAEvolutionStrategy`,
            in `evolution_strategy.py` from the `cma` module.
            
        """
        # TODO: be specific about the serial and the parallel case
        if number_to_ask == "all":
            number_to_ask = len(self._active_indices)
        assert number_to_ask > 0
        if number_to_ask > len(self._active_indices):
            number_to_ask = len(self._active_indices)
            warnings.warn("value larger than the number of active kernels {}. ".format(
                    len(self._active_indices)) + "Set to {}.".format(len(self._active_indices)))
        self.offspring = []
        res = [self.kernels[i].incumbent for i in self._told_indices]
        indices_to_ask = self._indices_to_ask(number_to_ask)
        for ikernel in indices_to_ask:
            kernel = self.kernels[ikernel]
            offspring = kernel.ask()
            res.extend(offspring)
            self.offspring += [(ikernel, offspring)]

        return res
        
    def tell(self, solutions, objective_values, constraints_values = []):
        """
        pass objective function values to update the state variables of some 
        kernels, `self._told_indices` and eventually `self.archive`.
        Arguments
        ---------
        `solutions`
            list or array of points (of type `numpy.ndarray`), most presumably 
            before delivered by the `ask()` method.
        `objective_values`
            list of multiobjective function values (of type `list`)
            corresponding to the respective points in `solutions`.
        `constraints_values`
            list of list of constraint values: each element is a list containing
            the values of one constraint function, that are obtained by evaluation
            on `solutions`.
            

        Details
        -------
        To update a kernel, `tell()` applies the kernel's `tell` method
        to the kernel's corresponding candidate solutions (offspring) along
        with the "changing" fitness `- self.pareto_front.hypervolume_improvement`.
        
        :See: 
            - the `tell` method from the class `cma.CMAEvolutionStrategy`,
            in `evolution_strategy.py` from the `cma` module.
            - the `hypervolume_improvement` method from the class
            `BiobjectiveNondominatedSortedList`, in the module `moarchiving.py`
            - the `hypervolume_improvement` method from the class
            `NonDominatedList`, in the module `nondominatedarchive.py`
        """
        if len(solutions) == 0: # when asking a terminated kernel for example
            return 
        if self.NDA is None:
            self.NDA = BiobjectiveNondominatedSortedList if len(
                    objective_values[0]) == 2 else NonDominatedList
        for i in range(len(self._told_indices)):
            self.kernels[self._told_indices[i]].objective_values = objective_values[i]
        
        if self.reference_point is None:
            pass #write here the max among the kernel.objective_values       
            
        start = len(self._told_indices) # position of the first offspring
        self._told_indices = []
        for ikernel, offspring in self.offspring:
            front_observed = self.NDA([self.kernels[i].objective_values for i in range(self.num_kernels) if i != ikernel],
                         self.reference_point)
            hypervolume_improvements = [front_observed.hypervolume_improvement(
                    point) for point in objective_values[start:start+len(offspring)]]
            
            g_values = [constraint[start:start+len(offspring)] \
                        for constraint in constraints_values]
            penalized_f_values = RankPenalizedFitness([-float(u) for u in 
                                hypervolume_improvements], g_values)
            kernel = self.kernels[ikernel]
            kernel.tell(offspring, penalized_f_values())
#            kernel.tell(offspring, [-float(u) for u in hypervolume_improvements])
            
            # invistigate whether `kernel` hits its stopping criteria
            if kernel.stop():
                self._active_indices.remove(ikernel) # ikernel must be in `_active_indices`
                if self.restart is not None and "timeout" not in kernel.stop():
                    try:
                        kernel_to_add = self.restart(self)
                        self._told_indices += [self.num_kernels]
                        self.add(kernel_to_add)
                    except:
                        warnings.warn('check if `self.restart` is returning a CMAKernel')
            
            try:
                kernel.logger.add()
            except:
                pass
            kernel._last_offspring_f_values = objective_values[start:start+len(offspring)]
            
            start += len(offspring)
            
        self._told_indices += [u for (u,v) in self.offspring]
        
        current_hypervolume = self.pareto_front.hypervolume
        epsilon = abs(current_hypervolume - self.best_hypervolume_pareto_front)
        if epsilon:
            self.epsilon_hypervolume_pareto_front = min(self.epsilon_hypervolume_pareto_front, 
                                                        epsilon)
        self.best_hypervolume_pareto_front = max(self.best_hypervolume_pareto_front,
                                                 current_hypervolume)

        if self.isarchive:
            if not self.archive:
                self.archive = self.NDA(objective_values, self.reference_point)
            else:
                self.archive.add_list(objective_values)
        self.countiter += 1
        self.countevals += len(objective_values)
        
    @property
    def pareto_front(self):
        """
        """
        return self.NDA([kernel.objective_values for kernel in self.kernels \
                         if kernel.objective_values is not None],
                         self.reference_point)

    @property
    def pareto_set(self):
        """
        return the estimated Pareto set of the algorithm, among the kernels'
        incumbents.
        It's the pre-image of `self.pareto_front`.
        """
        return [kernel.incumbent for kernel in self.kernels if \
                kernel.objective_values in self.pareto_front]

    def stop(self):
        """
        return a nonempty dictionary when all kernels stop, containing all the
        termination status. Therefore it's solely ... on the kernels' `stop`
        method, which also return dictionaries.
        Return
        ------
        For example with 5 kernels, stop should return either None, or a `dict`
        of the form:
            {0: dict0,
             1: dict1,
             2: dict2,
             3: dict2,
             4: dict4},
        where each index `i` is a key which value is the `dict` instance
        `self.kernels[i].stop()`
        """
        res = {}
        for i in range(self.num_kernels):
            if self.kernels[i].stop():
                res[i] = self.kernels[i].stop()
            else:
                return False
        return res
            
    @property 
    def termination_status(self):
        """
        return a dictionary of the current termination states of the kernels.
        
        """
        res = {}
        for i in range(self.num_kernels):
            res[i] = self.kernels[i].stop()
        return res
    
    def add(self, kernels):
        """
        add `kernels` of type `list` to `self.kernels` and update `self.pareto_front`
        and `self.num_kernels`.
        Generally, `kernels` are created from a factory function.
        If `kernels` is of length 1, the brackets can be omitted.
        """
        if not isinstance(kernels, list):
            kernels = [kernels]
        self.kernels += kernels
        self.num_kernels += len(kernels)
        # update `_active_indices` from scratch: inactive kernels might be added
        self._active_indices = [idx for idx in range(self.num_kernels) if \
                                not self.kernels[idx].stop()]
        self._ratio_nondom_offspring_incumbent = self.num_kernels * [0] # self.num_kernels changed
        
    def remove(self, kernels):
        """
        remove elements of the `kernels` (type `list`) that belong to
        `self.kernels`, and update `self.pareto_front` and
        `self.num_kernels` accordingly.
        If `kernels` is of length 1, the brackets can be omitted.
        """
        if not isinstance(kernels, list):
            kernels = [kernels]
        for kernel in kernels:
            if kernel in self.kernels:
                self.kernels.remove(kernel)
                if kernel.objective_values in self.pareto_front:
                    self.pareto_front.remove(kernel.objective_values)
            self.num_kernels -= 1
        # update `_active_indices`
        self._active_indices = [idx for idx in range(self.num_kernels) if \
                                not self.kernels[idx].stop()]

    @property
    def median_stds(self):
        """
        """
        tab = []
        res = []
        for kernel in self.kernels:
            conv = np.sqrt(kernel.dC)
            vec = []
            for i in range(len(kernel.pc)):
                xi = max(kernel.sigma_vec*kernel.pc[i], kernel.sigma_vec*conv[i])
                vec += [kernel.sigma * xi / kernel.sigma0]
            tab += [sorted(vec)]
        for i in range(len(tab[0])):
            vec = [u[i] for u in tab]
            res += [np.median(vec)]
        return res

    @property
    def max_max_stds(self):
        """
        """
        res = 0.0
        for kernel in self.kernels:
            conv = np.sqrt(kernel.dC)
            vec = []
            for i in range(len(kernel.pc)):
                xi = max(kernel.sigma_vec*kernel.pc[i], kernel.sigma_vec*conv[i])
                vec += [kernel.sigma * xi / kernel.sigma0]
            res = max(res, max(vec))
        return res    
    
    def _indices_to_ask(self, number_to_ask):
        """
        """
        sorted_indices = sorted(self._remaining_indices_to_ask, key = self.key_sort_indices)
        indices_to_ask = []
        remaining_indices = []
        if number_to_ask <= len(sorted_indices):
            indices_to_ask = sorted_indices[:number_to_ask]
            remaining_indices = sorted_indices[number_to_ask:]
        else:
            val = number_to_ask - len(sorted_indices)
            indices_to_ask = sorted_indices
            sorted_indices = sorted(self._active_indices, key = self.key_sort_indices)
            indices_to_ask += sorted_indices[:val]
            remaining_indices = sorted_indices[val:]
        
        self._remaining_indices_to_ask = remaining_indices
        return indices_to_ask
    
    def inactivate(self, kernel):
        """
        inactivate `kernel`, assuming that it's an element of `self.kernels`,
        or an index in `range(self.num_kernels)`.
        When inactivated, `kernel` is no longer updated, it is ignored.
        However we do not remove it from `self.kernels`, meaning that `kernel`
        might still play a role, due to its eventual trace in `self.pareto_front`.
    
        """
        if kernel in self.kernels:
            ikernel = self.kernels.index(kernel)

        try:
            self._active_indices.remove(ikernel)
            self.kernels[ikernel].opts['termination_callback'] += (lambda _: 'kernel turned off',)
        except (AttributeError, TypeError, KeyError, ValueError):
            warnings.warn("check again if `opts['termination_callback']` is"+
                          " correctly used, or if the kernel is not already"+
                          " turned off.")
            
    def activate(self, kernel):
        """
        activate `kernel` when it was inactivated beforehand. Otherwise 
        it remains quiet.
        
        We expect the kernel's `stop` method in interest to look like:
        kernel.stop() = {'callback': ['kernel turned off']}
        """
        raise NotImplementedError
        if kernel in self.kernels:
            ikernel = self.kernels.index(kernel)
        new_list = [callback for callback in self.kernels[ikernel].opts['termination_callback']\
                if callback(kernel) == 'kernel turned off']
        kernel.opts['termination_callback'] = new_list
        if not kernel.stop():
            self._active_indices += [ikernel]

    # The following methods 'disp_annotation' and 'disp' are from the 'cma'
    # module
    def disp_annotation(self):
        """
        copy-pasted from `cma.evolution_strategy`.
        print annotation line for `disp` ()"""
        self.has_been_called = True
        print('Iterat #Fevals   Hypervolume   axis ratios '
             '  sigmas   min&max stds\n'+'(median)'.rjust(42) +
             '(median)'.rjust(10) + '(median)'.rjust(12))

    def disp(self, modulo=None):
        """
        copy-pasted from `cma.evolution_strategy`.
        print current state variables in a single-line.
        copy-pasted from `cma.evolution_strategy` module

        Prints only if ``iteration_counter % modulo == 0``.

        :See also: `disp_annotation`.
        """
        if modulo is None:
            modulo = self.opts['verb_disp']

        # console display

        if modulo:
            if not hasattr(self, 'has_been_called'):
                self.disp_annotation()

            if self.countiter > 0 and (self.stop() or self.countiter < 4
                              or self.countiter % modulo < 1):
                try:
                    print(' '.join((repr(self.countiter).rjust(5),
                                    repr(self.countevals).rjust(6),
                                    '%.15e' % (self.pareto_front.hypervolume),
                                    '%4.1e' % (np.median([kernel.D.max() / kernel.D.min()
                                               if not kernel.opts['CMA_diagonal'] or kernel.countiter > kernel.opts['CMA_diagonal']
                                               else max(kernel.sigma_vec*1) / min(kernel.sigma_vec*1) \
                                               for kernel in self.kernels])),
                                    '%6.2e' % (np.median([kernel.sigma for kernel in self.kernels])),
                                    '%6.0e' % (np.median([kernel.sigma * min(kernel.sigma_vec * kernel.dC**0.5) \
                                                         for kernel in self.kernels])),
                                    '%6.0e' % (np.median([kernel.sigma * max(kernel.sigma_vec * kernel.dC**0.5) \
                                                          for kernel in self.kernels]))
                                    )))
                except AttributeError:
                    pass
                    # if self.countiter < 4:
       #         try:
                  #  sys.stdout.flush() : error in matlab:
                  # Python Error: AttributeError: 'MexPrinter' object has no attribute 'flush'

         #       except AttributeError:
          #          pass
        return self
    
    
def random_restart_kernel(moes, x0_fct=None, sigma0=None, **kwargs):
    """return a new "random" kernel"""
    if x0_fct is not None:
        x0 = x0_fct(moes.dimension)  # or however we can access the current search space dimension
    else:
        x0 = 2 * np.zeros(moes.dimension) - 1  # or whatever we want as default
    if sigma0 is None: 
        kernel = moes.kernels[0]
        sigma0 = kernel.sigma0 / 1.  # decrease the initial  step-size ?
    return get_cmas(x0, sigma0, number_created_kernels = moes.num_kernels)
    
def best_chv_restart_kernel(moes, sigma_factor=2, **kwargs):
    """return a new kernel derived from the kernel with largest contributing HV"""

    hvc = []
    for idx in range(moes.num_kernels):
        front = moes.NDA([moes.kernels[i].objective_values for i in range(moes.num_kernels) if i != idx],
                            moes.reference_point)
        f_pair = moes.kernels[idx].objective_values
        hvc += [front.hypervolume_improvement(f_pair)]
    sorted_indices = sorted(range(moes.num_kernels), key=lambda i: - hvc[i])
    my_front = moes.pareto_front
    idx_best = sorted_indices[0]
    if len(my_front) > 1:
        for i in sorted_indices:
            kernel = moes.kernels[i]
            if kernel.stop() or kernel.objective_values not in [my_front[0], my_front[-1]]:
                idx_best = i
                break
    ker = moes.kernels[idx_best]
    return ker._copy_light(sigma=sigma_factor * ker.sigma, inopts={'verb_filenameprefix': 'cma_kernels' + os.sep + 
                        str(moes.num_kernels)})

# callbacks for sorting indices to pick in the `tell` method
        
def sort_even_odds(i):
    """
    """
    return i % 2

def sort_odds_even(i):
    """
    """
    return - (i % 2)

def sort_random(i):
    """
    """
    return np.random.rand()

def sort_increasing(i):
    """
    """
    return i

def sort_decreasing(i):
    """
    """
    return - i

def get_cmas(x_starts, sigma_starts, inopts = None, number_created_kernels = 0):
    """
    produce `len(x_starts)` instances of type `cmaKernel`.
    """
    
    if x_starts is not None and len(x_starts):
        try:
            x_starts = x_starts.tolist()
        except:
            pass
        try:
            x_starts = [u.tolist() for u in x_starts]
        except:
            pass
        if not isinstance(x_starts[0], list):
            x_starts = [x_starts]
    
    kernels = []
    num_kernels = len(x_starts)
    if not isinstance(sigma_starts, list):
        sigma_starts = num_kernels * [sigma_starts]
    if inopts is None:
        inopts = {}
    list_of_opts = []
    if isinstance(inopts, list):
        list_of_opts = inopts
    else:
        list_of_opts = [dict(inopts) for _ in range(num_kernels)]
    
    # repairing the initial values:
    for i in range(len(x_starts)):
        try:
            bounds_transform = cma.constraints_handler.BoundTransform(list_of_opts[i]['bounds'])        
            x_starts[i] = bounds_transform.repair(x_starts[i])
        except KeyError:
            pass
    
    for i in range(num_kernels):
        defopts = cma.CMAOptions()
        defopts.update({'verb_filenameprefix': 'cma_kernels' + os.sep + 
                        str(number_created_kernels+i), 'conditioncov_alleviate': [np.inf, np.inf],
                    'verbose': -1, 'tolx': 1e-4})  
        if isinstance(list_of_opts[i], dict):
            defopts.update(list_of_opts[i])
            
        kernels += [CmaKernel(x_starts[i], sigma_starts[i], defopts)]
        
    return kernels

class CmaKernel(cma.CMAEvolutionStrategy):
    """
    inheriting from the `cma.CMAEvolutionStrategy` class, by slightly modifying
    the `stop` method, and adding the property `incumbent` and 
    the attribute `objective_values`.
    """
    def __init__(self, x0, sigma0, inopts=None):
        """
        Arguments
        =========
        `x0`
            initial solution, starting point. `x0` is given as "phenotype"
            which means, if::
    
                opts = {'transformation': [transform, inverse]}
    
            is given and ``inverse is None``, the initial mean is not
            consistent with `x0` in that ``transform(mean)`` does not
            equal to `x0` unless ``transform(mean)`` equals ``mean``.
        `sigma0`
            initial standard deviation.  The problem variables should
            have been scaled, such that a single standard deviation
            on all variables is useful and the optimum is expected to
            lie within about `x0` +- ``3*sigma0``. See also options
            `scaling_of_variables`. Often one wants to check for
            solutions close to the initial point. This allows,
            for example, for an easier check of consistency of the
            objective function and its interfacing with the optimizer.
            In this case, a much smaller `sigma0` is advisable.
        `inopts`
            options, a dictionary with optional settings,
            see class `cma.CMAOptions`.
        """
        cma.CMAEvolutionStrategy.__init__(self, x0, sigma0, inopts)
        self.objective_values = None # the objective value of self's incumbent
        # (see below for definition of incumbent)
        self._last_offspring_f_values = None # the fvalues of its offspring
        # used in the last call of `tell`.  
    
    @property
    def incumbent(self):
        """
        it gives the 'repaired' mean of a cma-es. For a problem with bound
        constraints, `self.incumbent` in inside the bounds.
        """
        return self.boundary_handler.repair(self.mean)
    
    def stop(self, check=True, ignore_list=()):
        """
        'flat fitness' is ignored because it does not necessarily mean that a 
        termination criteria is met. For the `cigtab` bi-objective
        function for example, the Hypervolume is flat for a long period, 
        although the evolution is correctly occuring in the search space.
        """
        to_be_ignored = ignore_list + ('tolfun', 'tolfunhist', 
                                       'flat fitness', 'tolstagnation')
        
        return cma.CMAEvolutionStrategy.stop(self, check, ignore_list = to_be_ignored)
    
    def _copy_light(self, sigma=None, inopts=None):
        """tentative copy of self, versatile (interface and functionalities may change).
        
        This may not work depending on the used sampler.
        
        Copy mean and sample distribution parameters and input options.

        Do not copy evolution paths, termination status or other state variables.
        """
        es = super(CmaKernel, self)._copy_light(sigma, inopts)

        es.objective_values = self.objective_values
        es._last_offspring_f_values = self._last_offspring_f_values
        return es  
    
class FitFun:
    """
    Define a callable multiobjective function from single objective ones.
    Example:
        fitness = como.FitFun(cma.ff.sphere, lambda x: cma.ff.sphere(x-1)).
    """
    def __init__(self, *args):
        self.callables = args
    def __call__(self, x):
        return [f(x) for f in self.callables]

class RankPenalizedFitness:
    """compute f-values of infeasible solutions as rank_f-inverse(const + sum g-ranks).
    
    The inverse is computed by linear interpolation.
    
    Draw backs: does not support approaching the optimum from the infeasible domain.
    
    Infeasible solutions with valid f-value measurement could get a 1/2-scaled credit for their
    f-rank difference to the base f-value.
    """

    def __init__(self, f_values, g_list_values):
        self.f_values = f_values
        self.g_list_values = g_list_values
        # control parameters
        self.base_prctile = 0.2  # best f-value an infeasible solution can get
        self.g_scale = 1.01  # factor for g-ranks penalty
        self._debugging = False
        # internal state
        self.f_current_best = 0

    def __call__(self):
        """
        Assumes that at least one solution does not return nan as f-value
        """
        # TODO: what to do if there is no f-value for a feasible solution
     #   f_values = [self.f(x) for x in X]
        f_values = self.f_values
        g_ranks_list = []
        is_feasible = np.ones(len(f_values))
   #     for g in self.g_list:
        for g_values in self.g_list_values:
    #        g_values = [g(x) for x in X]         
            g_is_feas = np.asarray(g_values) <= 0
            is_feasible *= g_is_feas
            nb_feas = sum(g_is_feas)
            g_ranks = [g - nb_feas + 1 if g >= nb_feas else 0
                       for g in cma.utilities.utils.ranks(g_values)]  # TODO: this fails with nan-values
            if self._debugging: print(g_ranks)
            g_ranks_list.append(g_ranks)
        idx_feas = np.where(is_feasible)[0]
        # we could also add the distance to the best feasible solution as penalty on the median?
        # or we need to increase the individual g-weight with the number of iterations that no single
        #    feasible value was seen
        # change f-values of infeasible solutions
        sorted_feas_f_values = sorted(np.asarray(f_values)[idx_feas])
        try: self.f_current_best = sorted_feas_f_values[0]
        except IndexError: pass
        j0 = self.base_prctile * (len(idx_feas) - 1)
        #         for i in set(range(len(X))).difference(idx_feas):
        for i in set(range(len(f_values))).difference(idx_feas):
            j = j0 + self.g_scale * (
                    sum(g_ranks[i] for g_ranks in g_ranks_list) - 1)  # -1 makes base a possible value
            assert j >= self.base_prctile * (len(idx_feas) - 1)
            # TODO: use f-value of infeasible solution if available?
            if 11 < 3 and np.isfinite(f_values[i]):
                self.gf_scale = 1 / 2
                j += self.gf_scale * (_interpolated_rank(f_values, f_values[i]) - 
                                      _interpolated_rank(f_values, f_values[j0]))  # TODO: filter f-values by np.isfinite
            j = max((j, 0))
            j1, j2 = int(j), int(np.ceil(j))
            f1 = self._f_from_index(sorted_feas_f_values, j1)
            f2 = self._f_from_index(sorted_feas_f_values, j2)
            # take weighted average fitness between index j and j+1
            f_values[i] = 0e-6 + (j - j1) * f2 + (j2 - j) * f1 if j2 > j1 else f1
        return f_values

    def _f_from_index(self, f_values, i):
        """`i` must be an integer but may be ``>= len(f_values)``"""
        imax = len(f_values) - 1
        if imax < 0:  # no feasible f-value
            return self.f_current_best + i
        return f_values[min((imax, i))] + max((i - imax, 0))
        
