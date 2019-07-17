#  Copyright (c) 2019 Toyota Research Institute.  All rights reserved.

import traceback
import pandas as pd
import os

from monty.serialization import dumpfn
from camd.domain import StructureDomain
from camd.agent.agents import AgentStabilityML5
from camd.agent.base import RandomAgent
from camd.analysis import AnalyzeStability
from camd.experiment import ATFSampler
from camd.loop import Loop
from camd import CAMD_TEST_FILES

from camd.analysis import AnalyzeStability_mod
from camd.experiment.dft import OqmdDFTonMC1
from sklearn.neural_network import MLPRegressor
import pickle


__version__ = "2019.07.15"


def run_dft_campaign(chemsys, s3_prefix=None):
    """

    Args:
        chemsys (List): list of elements in which to do
            the chemsys

    Returns:
        (bool): True if run exits

    """
    # Get structure domain
    domain = StructureDomain.from_bounds(
        chemsys, n_max_atoms=12, **{'grid': range(1, 3)})
    candidate_data = domain.candidates()
    structure_dict = domain.hypo_structures_dict

    # Dump structure/candidate data
    with open('candidate_data.pickle', 'wb') as f:
        pickle.dump(candidate_data, f)
    with open('structure_dict.pickle', 'wb') as f:
        pickle.dump(structure_dict, f)

    # Set up agents and loop parameters
    agent = AgentStabilityML5  # Query-by-committee agent that operates with maximum expected gain
    agent_params = {
        'ML_algorithm': MLPRegressor,  # We'll use a simple NN regressor
        'ML_algorithm_params': {'hidden_layer_sizes': (84, 50)},
        'N_query': 10,  # Number of experiments the agent can request in each round.
        'hull_distance': 0.25,  # Distance to hull to consider a finding as discovery (eV/atom)
        'frac': 0.7  # Fraction to exploit
    }
    analyzer = AnalyzeStability_mod
    analyzer_params = {'hull_distance': 0.2}  # analysis criterion (need not be exactly same as agent's goal)
    experiment = OqmdDFTonMC1
    experiment_params = {'structure_dict': structure_dict, 'candidate_data': candidate_data, 'timeout': 20000}
    experiment_params.update({'timeout': 30000})

    # Construct and start loop
    new_loop = Loop(
        candidate_data, agent, experiment, analyzer, agent_params=agent_params,
        analyzer_params=analyzer_params, experiment_params=experiment_params,
        s3_prefix=s3_prefix)
    try:
        new_loop.auto_loop_in_directories(
            n_iterations=5, timeout=10, monitor=True,
            initialize=True, with_icsd=True)
    except Exception as e:
        error_msg = {"error": "{}".format(e),
                     "traceback": traceback.format_exc()}
        dumpfn(error_msg, "error.json")
        new_loop.s3_sync()

    return True


def run_atf_campaign(s3_prefix):
    df = pd.read_csv(os.path.join(CAMD_TEST_FILES, 'test_df.csv'))
    n_seed = 200  # Starting sample size
    n_query = 10  # This many new candidates are "calculated with DFT" (i.e. requested from Oracle -- DFT)
    agent = RandomAgent
    agent_params = {'hull_distance': 0.05, 'N_query': n_query}
    analyzer = AnalyzeStability
    analyzer_params = {'hull_distance': 0.05}
    experiment = ATFSampler
    experiment_params = {'dataframe': df}
    candidate_data = df
    new_loop = Loop(candidate_data, agent, experiment, analyzer,
                    agent_params=agent_params, analyzer_params=analyzer_params,
                    experiment_params=experiment_params,
                    create_seed=n_seed, s3_prefix=s3_prefix)

    new_loop.initialize()

    for _ in range(3):
        new_loop.run()

    return True
