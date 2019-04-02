# Copyright Toyota Research Institute 2019

import numpy as np
from tqdm import tqdm
from qmpy import PhaseSpace, Phase, PhaseData
from abc import ABCMeta
import multiprocessing

ELEMENTS = ["Pr", "Ru", "Th", "Pt", "Ni", "S", "Na", "Nb", "Nd", "C", "Li", "Pb", "Y", "Tl", "Lu", "Rb", "Ti", "Np",
            "Te", "Rh", "Tc", "La", "Ta", "Be", "Sr", "Sm", "Ba", "Tb", "Yb", "Bi", "Re", "Pu", "Fe", "Br", "Dy", "Pd",
            "Hf", "Hg", "Ho", "Mg", "B", "Pm", "P", "F", "I", "H", "K", "Mn", "Ac", "O", "N", "Eu", "Si", "U", "Sn",
            "W", "V", "Sc", "Sb", "Mo", "Os", "Se", "Zn", "Co", "Ge", "Ag", "Cl", "Ca", "Ir", "Al", "Ce", "Cd", "Pa",
            "As", "Gd", "Au", "Cu", "Ga", "In", "Cs", "Cr", "Tm", "Zr", "Er"]


#TODO: Eval Performance = start / stop?

class AnalysisBase:
    __metaclass__ = ABCMeta

    def analysis(self):
        pass


class AnalyzeStability(AnalysisBase):
    def __init__(self, df, new_result_ids, hull_distance=None, multiprocessing=True):
        self.df = df
        self.new_result_ids = new_result_ids
        self.hull_distance = hull_distance if hull_distance else 0.05
        self.multiprocessing = multiprocessing
        super(AnalyzeStability, self).__init__()

    def analysis(self):
        phases = []
        for data in self.df.iterrows():
            phases.append(Phase(data[1]['Composition'], energy=data[1]['delta_e'], per_atom=True, description=data[0]))
        for el in ELEMENTS:
            phases.append(Phase(el, 0.0, per_atom=True))

        pd = PhaseData()
        pd.add_phases(phases)
        space = PhaseSpaceAL(bounds=ELEMENTS, data=pd)
        if self.multiprocessing:
            space.compute_stabilities_multi()
        else:
            space.compute_stabilities_mod()

        stabilities_of_space_uids = np.array([p.stability for p in space.phases]) <= self.hull_distance

        stabilities_of_new = {}
        for _p in space.phases:
            if _p.description in self.new_result_ids:
                stabilities_of_new[_p.description] = _p.stability

        stabilities_of_new_uids = np.array([stabilities_of_new[uid] for uid in self.new_result_ids]) <= self.hull_distance

        # array of bools for stable vs not for new uids, and all experiments, respectively
        return stabilities_of_new_uids, stabilities_of_space_uids


class PhaseSpaceAL(PhaseSpace):
    """
    Modified qmpy.PhaseSpace for GCLP based stabiltiy computations
    TODO: basic multithread or Gurobi for gclp
    """

    def compute_stabilities_mod(self, phases_to_evaluate=None):
        """
        Calculate the stability for every Phase.
        Keyword Arguments:
            phases:
                List of Phases. If None, uses every Phase in PhaseSpace.phases
            save:
                If True, save the value for stability to the database.
            new_only:
                If True, only compute the stability for Phases which did not
                import a stability from the OQMD. False by default.
        """

        if phases_to_evaluate is None:
            phases_to_evaluate = self.phases

        for p in tqdm(self.phase_dict.values()):
            if p.stability is None:  # for low e phases, we only need to eval stability if it doesn't exist
                try:
                    p.stability = p.energy - self.gclp(p.unit_comp)[0]
                except:
                    print p
                    p.stability = np.nan

        # will only do requested phases for things not in phase_dict
        for p in tqdm(phases_to_evaluate):
            if p not in self.phase_dict.values():
                if p.name in self.phase_dict:
                    p.stability = p.energy - self.phase_dict[p.name].energy + self.phase_dict[p.name].stability
                else:
                    try:
                        p.stability = p.energy - self.gclp(p.unit_comp)[0]
                    except:
                        print p
                        p.stability = np.nan

    def compute_stabilities_multi(self, phases_to_evaluate=None, ncpus=multiprocessing.cpu_count()):
        """
        Calculate the stability for every Phase.
        Keyword Arguments:
            phases:
                List of Phases. If None, uses every Phase in PhaseSpace.phases
            save:
                If True, save the value for stability to the database.
            new_only:
                If True, only compute the stability for Phases which did not
                import a stability from the OQMD. False by default.
        """

        if phases_to_evaluate is None:
            phases_to_evaluate = self.phases

        # Creating a map from entry uid to index of entry in the current list of phases in space.
        self.uid_to_phase_ind = dict([(self.phases[i].description, i) for i in range(len(self.phases))])

        phase_dict_list = self.phase_dict.values()
        _result_list1 = parmap(self._multiproc_help1,  phase_dict_list, nprocs=ncpus)
        for i in range(len(phase_dict_list)):
            self.phase_dict[phase_dict_list[i].name].stability = _result_list1[i]

        _result_list2 = parmap(self._multiproc_help2, phases_to_evaluate, nprocs=ncpus)
        for i in range(len(phases_to_evaluate)):
            # we will use the uid_to_phase_ind create above to be able to map results of parmap to self.phases
            ind = self.uid_to_phase_ind[phases_to_evaluate[i].description]
            self.phases[ind].stability = _result_list2[i]


    def _multiproc_help1(self, p):
        if p.stability is None:  # for low e phases, we only need to eval stability if it doesn't exist
            try:
                p.stability = p.energy - self.gclp(p.unit_comp)[0]
            except:
                print p
                p.stability = np.nan
        return p.stability

    def _multiproc_help2(self, p):
        if p not in self.phase_dict.values():
            if p.name in self.phase_dict:
                p.stability = p.energy - self.phase_dict[p.name].energy + self.phase_dict[p.name].stability
            else:
                try:
                    p.stability = p.energy - self.gclp(p.unit_comp)[0]
                except:
                    print p
                    p.stability = np.nan
        return p.stability


def fun(f, q_in, q_out):
    while True:
        i, x = q_in.get()
        if i is None:
            break
        q_out.put((i, f(x)))


def parmap(f, X, nprocs=multiprocessing.cpu_count()):
    q_in = multiprocessing.Queue(1)
    q_out = multiprocessing.Queue()

    proc = [multiprocessing.Process(target=fun, args=(f, q_in, q_out))
            for _ in range(nprocs)]
    for p in proc:
        p.daemon = True
        p.start()

    sent = [q_in.put((i, x)) for i, x in enumerate(X)]
    [q_in.put((None, None)) for _ in range(nprocs)]
    res = [q_out.get() for _ in range(len(sent))]

    [p.join() for p in proc]

    return [x for i, x in sorted(res)]