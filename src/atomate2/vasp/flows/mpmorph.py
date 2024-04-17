"""Flows adapted from MPMorph *link to origin github repo*"""  # TODO: Add link to origin github repo

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jobflow import Response

from atomate2.common.flows.mpmorph import (
    FastQuenchMaker,
    SlowQuenchMaker,
    MPMorphMDMaker,
    EquilibriumVolumeMaker,
)

from atomate2.vasp.flows.md import MultiMDMaker
from atomate2.vasp.jobs.md import MDMaker
from atomate2.vasp.jobs.mpmorph import (
    BaseMPMorphMDMaker,
    SlowQuenchVaspMaker,
    FastQuenchVaspMaker,
)

from atomate2.vasp.powerups import update_user_incar_settings

from atomate2.vasp.jobs.mp import (
    MPMetaGGARelaxMaker,
    MPMetaGGAStaticMaker,
    MPPreRelaxMaker,
)

import math

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pymatgen.core import Structure
    from pathlib import Path
    from jobflow import Flow, Maker


@dataclass
class BaseMPMorphVaspMDMaker(MPMorphMDMaker):
    """Base VASP MPMorph flow for volume equilibration, quench, and production runs via molecular dynamics

    Calculates the equilibrium volume of a structure at a given temperature. A convergence fitting
    (optional) for the volume followed by quench (optional) from high temperature to low temperature
    and finally a production run(s) at a given temperature. Production run is broken up into multiple
    smaller steps to ensure simulation does not hit wall time limits.

    Check atomate2.common.flows.mpmorph for MPMorphMDMaker

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    temperature : int = 300
        Temperature of the equilibrium volume search and production run in Kelvin, default 300K
    end_temp : int = 300
        End temperature of the equilibrium volume search and production run in Kelvin, default 300K. Use only for lowering temperarture for production run
    md_maker : BaseMPMorphMDMaker
        MDMaker to generate the molecular dynamics jobs specifically for MPMorph AIMD; inherits from MDMaker (VASP)
    steps_convergence: int | None = None
        Defaults to 5000 steps unless specified
    steps_single_production_run: int | None = 5000
        Number of steps for a single production run; default 5000 steps. If set and steps_total_production > steps_single_production_run, multiple production runs (MultiMDMaker) will be generated
    steps_total_production: int = 10000
        Total number of steps for the production run(s); default 10000 steps
    convergence_md_maker : EquilibrateVolumeMaker
        MDMaker to generate the equilibrium volumer searcher; inherits from EquilibriumVolumeMaker and MDMaker (VASP)
    production_md_maker : BaseMPMorphMDMaker
        MDMaker to generate the production run(s); inherits from MDMaker (VASP) or MultiMDMaker
    quench_maker :  SlowQuenchMaker or FastQuenchMaker or None
        SlowQuenchMaker - MDMaker that quenchs structure from high temperature to low temperature
        FastQuenchMaker - DoubleRelaxMaker + Static that "quenchs" structure at 0K
    """

    name: str = "MP Morph VASP Skeleton MD Maker"
    temperature: int = 300
    end_temp: int = 300
    steps_convergence: int | None = None
    steps_single_production_run: int | None = 5000
    steps_total_production: int = 10000

    md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    convergence_md_maker: EquilibriumVolumeMaker | None = None
    production_md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)

    quench_maker: FastQuenchVaspMaker | SlowQuenchVaspMaker | None = None

    def _post_init_update(self) -> None:
        """ Ensure that VASP input sets correctly set temperature. """

        # TODO: check if this properly updates INCAR for all MD runs
        if self.steps_convergence is None:
            self.md_maker = update_user_incar_settings(
                flow=self.md_maker,
                incar_updates={
                    "TEBEG": self.temperature,
                    "TEEND": self.temperature,  # Equilibrium volume search is only at single temperature (temperature sweep not allowed)
                },
            )
        elif (
            self.steps_convergence is not None
        ):  # TODO: make this elif statement more efficient
            self.md_maker = update_user_incar_settings(
                flow=self.md_maker,
                incar_updates={
                    "TEBEG": self.temperature,
                    "TEEND": self.end_temp,
                    "NSW": self.steps_convergence,
                },
            )
        self.convergence_md_maker = EquilibriumVolumeMaker(
            name="MP Morph VASP Equilibrium Volume Maker", md_maker=self.md_maker
        )

        if self.steps_single_production_run is None:
            self.steps_single_production_run = self.steps_total_production

        self.production_md_maker = update_user_incar_settings(
            flow=self.production_md_maker,
            incar_updates={
                "TEBEG": self.temperature,
                "TEEND": self.end_temp,
                "NSW": self.steps_single_production_run,
            },
        )

        if self.steps_total_production > self.steps_single_production_run:
            n_prod_md_steps = math.ceil(
                self.steps_total_production / self.steps_single_production_run
            )
            self.production_md_maker = Response(
                replace=MultiMDMaker(
                    md_makers=[self.production_md_maker for _ in range(n_prod_md_steps)]
                )
            )

@dataclass
class MPMorphVaspMDMaker(BaseMPMorphVaspMDMaker):
    """Skeleton VASP MPMorph flow for volume equilibration and single production run via molecular dynamics

    Calculates the equilibrium volume of a structure at a given temperature. A convergence fitting
    for the volume and finally a production run at a given temperature.

    Check atomate2.common.flows.mpmorph for MPMorphMDMaker

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    temperature : int = 300
        Temperature of the equilibrium volume search and production run in Kelvin, default 300K
    end_temp : int = 300
        End temperature of the equilibrium volume search and production run in Kelvin, default 300K. Use only for lowering temperarture for production run
    md_maker : BaseMPMorphMDMaker
        MDMaker to generate the molecular dynamics jobs specifically for MPMorph AIMD; inherits from MDMaker (VASP)
    steps_convergence: int | None = None
        Defaults to 5000 steps unless specified
    steps_single_production_run: int | None = None
        This maker only generates a single production run; check skeleton or MPMorphVASPMultiMDMaker for multiple production runs
    steps_total_production: int = 10000
        Total number of steps for the production run(s); default 10000 steps
    production_md_maker : BaseMPMorphMDMaker
        MDMaker to generate the production run(s); inherits from MDMaker (VASP) or MultiMDMaker
    """

    name: str = "MP Morph VASP MD Maker"
    temperature: int = 300
    end_temp: int = 300
    steps_convergence: int | None = None
    steps_single_production_run: int | None = None
    steps_total_production: int = 10000

    md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    production_md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)


@dataclass
class MPMorphVaspMultiMDMaker(BaseMPMorphVaspMDMaker):
    """VASP MPMorph flow for volume equilibration and multiple production runs via molecular dynamics

    Calculates the equilibrium volume of a structure at a given temperature. A convergence fitting
    for the volume and finally a production run at a given temperature.

    Check atomate2.common.flows.mpmorph for MPMorphMDMaker

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    temperature : int = 300
        Temperature of the equilibrium volume search and production run in Kelvin, default 300K
    end_temp : int = 300
        End temperature of the equilibrium volume search and production run in Kelvin, default 300K. Use only for lowering temperarture for production run
    md_maker : BaseMPMorphMDMaker
        MDMaker to generate the molecular dynamics jobs specifically for MPMorph AIMD; inherits from MDMaker (VASP)
    steps_convergence: int | None = None
        Defaults to 5000 steps unless specified
    steps_single_production_run: int | None = 5000
        Number of steps for a single production run; default 5000 steps. If set and steps_total_production > steps_single_production_run, multiple production runs (MultiMDMaker) will be generated
    steps_total_production: int = 10000
        Total number of steps for the production run(s); default 10000 steps (in this default 10000/5000 = 2 individual production runs)
    production_md_maker : BaseMPMorphMDMaker
        MDMaker to generate the production run(s); inherits from MDMaker (VASP) or MultiMDMaker
    """

    name: str = "MP Morph VASP Multi MD Maker"
    temperature: int = 300
    end_temp: int = 300
    steps_convergence: int | None = None
    steps_single_production_run: int | None = 5000
    steps_total_production: int = 10000

    md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    production_md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)


@dataclass
class MPMorphVaspMDSlowQuenchMaker(BaseMPMorphVaspMDMaker):
    """VASP MPMorph flow for volume equilibration, multiple production runs, and slow quench via molecular dynamics

    Calculates the equilibrium volume of a structure at a given temperature. A convergence fitting
    for the volume and finally a production run at a given temperature.

    Check atomate2.common.flows.mpmorph for MPMorphMDMaker

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    temperature : int = 300
        Temperature of the equilibrium volume search and production run in Kelvin, default 300K
    end_temp : int = 300
        End temperature of the equilibrium volume search and production run in Kelvin, default 300K. Use only for lowering temperarture for production run
    md_maker : BaseMPMorphMDMaker
        MDMaker to generate the molecular dynamics jobs specifically for MPMorph AIMD; inherits from MDMaker (VASP)
    steps_convergence: int | None = None
        Defaults to 5000 steps unless specified
    steps_single_production_run: int | None = 5000
        Number of steps for a single production run; default 5000 steps. If set and steps_total_production > steps_single_production_run, multiple production runs (MultiMDMaker) will be generated
    steps_total_production: int = 10000
        Total number of steps for the production run(s); default 10000 steps (in this default 10000/5000 = 2 individual production runs)
    production_md_maker : BaseMPMorphMDMaker
        MDMaker to generate the production run(s); inherits from MDMaker (VASP) or MultiMDMaker.
    quench_maker :  SlowQuenchVaspMaker
        SlowQuenchVaspMaker - MDMaker that quenchs structure from high temperature to low temperature in piece-wise AIMD runs. Check atomate2.vasp.jobs.mpmorph for SlowQuenchVaspMaker.
    """

    name: str = "MP Morph VASP MD Maker Slow Quench"
    temperature: int = 300
    end_temp: int = 300
    steps_convergence: int | None = None
    steps_single_production_run: int | None = 5000
    steps_total_production: int = 10000

    md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    production_md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    quench_maker: SlowQuenchVaspMaker = field(
        default_factory=lambda: SlowQuenchVaspMaker(
            quench_nsteps=1000,
            quench_temperature_step=500,
            quench_end_temperature=500,
            quench_start_temperature=3000,
        )
    )


@dataclass
class MPMorphVaspMDFastQuenchMaker(BaseMPMorphVaspMDMaker):
    """VASP MPMorph flow for volume equilibration, multiple production runs, and slow quench via molecular dynamics

    Calculates the equilibrium volume of a structure at a given temperature. A convergence fitting
    for the volume and finally a production run at a given temperature.

    Check atomate2.common.flows.mpmorph for MPMorphMDMaker

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    temperature : int = 300
        Temperature of the equilibrium volume search and production run in Kelvin, default 300K
    end_temp : int = 300
        End temperature of the equilibrium volume search and production run in Kelvin, default 300K. Use only for lowering temperarture for production run
    md_maker : BaseMPMorphMDMaker
        MDMaker to generate the molecular dynamics jobs specifically for MPMorph AIMD; inherits from MDMaker (VASP)
    steps_convergence: int | None = None
        Defaults to 5000 steps unless specified
    steps_single_production_run: int | None = 5000
        Number of steps for a single production run; default 5000 steps. If set and steps_total_production > steps_single_production_run, multiple production runs (MultiMDMaker) will be generated
    steps_total_production: int = 10000
        Total number of steps for the production run(s); default 10000 steps (in this default 10000/5000 = 2 individual production runs)
    production_md_maker : BaseMPMorphMDMaker
        MDMaker to generate the production run(s); inherits from MDMaker (VASP) or MultiMDMaker.
    quench_maker :  FastQuenchVaspMaker
        FastQuenchVaspMaker - MDMaker that quenchs structure from high temperature to 0K. Check atomate2.vasp.jobs.mpmorph for FastQuenchVaspMaker.
    """

    name: str = "MP Morph VASP MD Maker Fast Quench"
    temperature: int = 300
    end_temp: int = 300
    steps_convergence: int | None = None
    steps_single_production_run: int | None = 5000
    steps_total_production: int = 10000

    md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    production_md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)
    quench_maker: FastQuenchVaspMaker = field(default_factory=FastQuenchVaspMaker)


# TODO: Below is first version of MPMorphVaspMDMaker; remove once all other MPMorphVaspMDMaker are updated and tested
@dataclass
class MPMorphVaspOldMDMaker(MPMorphMDMaker):
    """Skeleton VASP MPMorph flow for volume equilibration, quench, and production runs via molecular dynamics

    Calculates the equilibrium volume of a structure at a given temperature. A convergence fitting
    (optional) for the volume followed by quench (optional) from high temperature to low temperature
    and finally a production run(s) at a given temperature. Production run is broken up into multiple
    smaller steps to ensure simulation does not hit wall time limits.

    Check atomate2.common.flows.mpmorph for MPMorphMDMaker

    Parameters
    ----------
    name : str
        Name of the flows produced by this maker.
    temperature : int = 300
        Temperature of the equilibrium volume search and production run in Kelvin, default 300K
    end_temp : int = 300
        End temperature of the equilibrium volume search and production run in Kelvin, default 300K. Use only for lowering temperarture for production run
    md_maker : BaseMPMorphMDMaker
        MDMaker to generate the molecular dynamics jobs specifically for MPMorph AIMD; inherits from MDMaker (VASP)
    steps_convergence: int | None = None
        Defaults to 5000 steps unless specified
    steps_single_production_run: int | None = 5000
        Number of steps for a single production run; default 5000 steps. If set and steps_total_production > steps_single_production_run, multiple production runs (MultiMDMaker) will be generated
    steps_total_production: int = 10000
        Total number of steps for the production run(s); default 10000 steps
    quench_tempature_setup: dict = None
        Only needed for SlowQuenchMaker. Setup for slow quenching the structure from high temperature to low temperature
        Example:
        quench_tempature_setup ={
            "start_temp": 3000, # Starting temperature for quench
            "end_temp": 500, # Ending temperature for quench
            "temp_step": 500, # Temperature step for quench
            "nsteps": 1000, # Number of steps for quench
        }
    convergence_md_maker : EquilibrateVolumeMaker
        MDMaker to generate the equilibrium volumer searcher; inherits from EquilibriumVolumeMaker and MDMaker (VASP)
    production_md_maker : BaseMPMorphMDMaker
        MDMaker to generate the production run(s); inherits from MDMaker (VASP) or MultiMDMaker
    quench_maker :  SlowQuenchMaker or FastQuenchMaker or None
        SlowQuenchMaker - MDMaker that quenchs structure from high temperature to low temperature
        FastQuenchMaker - DoubleRelaxMaker + Static that "quenchs" structure at 0K
    """

    name: str = "MP Morph VASP Skeleton MD Maker"
    temperature: int = 300
    end_temp: int = 300
    steps_convergence: int | None = None
    steps_single_production_run: int | None = 5000
    steps_total_production: int = 10000

    quench_tempature_setup: dict | None = None

    md_maker: MDMaker | None = field(default_factory=BaseMPMorphMDMaker)
    convergence_md_maker: EquilibriumVolumeMaker | None = None
    production_md_maker: MDMaker = field(default_factory=BaseMPMorphMDMaker)

    quench_maker: FastQuenchVaspMaker | SlowQuenchVaspMaker | None = None

    def make(self, structure: Structure, prev_dir: str | Path | None = None) -> Flow:

        # TODO: check if this properly updates INCAR for all MD runs
        if self.steps_convergence is None:
            self.md_maker = update_user_incar_settings(
                flow=self.md_maker,
                incar_updates={
                    "TEBEG": self.temperature,
                    "TEEND": self.temperature,  # Equilibrium volume search is only at single temperature (temperature sweep not allowed)
                },
            )
        elif (
            self.steps_convergence is not None
        ):  # TODO: make this elif statement more efficient
            self.md_maker = update_user_incar_settings(
                flow=self.md_maker,
                incar_updates={
                    "TEBEG": self.temperature,
                    "TEEND": self.end_temp,
                    "NSW": self.steps_convergence,
                },
            )
        self.convergence_md_maker = EquilibriumVolumeMaker(
            name="MP Morph VASP Equilibrium Volume Maker", md_maker=self.md_maker
        )

        if self.steps_single_production_run is None:
            self.steps_single_production_run = self.steps_total_production

        self.production_md_maker = update_user_incar_settings(
            flow=self.production_md_maker,
            incar_updates={
                "TEBEG": self.temperature,
                "TEEND": self.end_temp,
                "NSW": self.steps_single_production_run,
            },
        )

        if self.steps_total_production > self.steps_single_production_run:
            n_prod_md_steps = math.ceil(
                self.steps_total_production / self.steps_single_production_run
            )
            self.production_md_maker = Response(
                replace=MultiMDMaker(
                    md_makers=[self.production_md_maker for _ in range(n_prod_md_steps)]
                )
            )

        if self.quench_maker is not None:
            if isinstance(self.quench_maker, SlowQuenchMaker):
                self.quench_maker = SlowQuenchMaker(
                    md_maker=self.md_maker,
                    quench_tempature_setup=self.quench_tempature_setup,
                )
            elif isinstance(self.quench_maker, FastQuenchMaker):
                self.quench_maker = FastQuenchMaker(
                    relax_maker=MPPreRelaxMaker,
                    relax_maker2=MPMetaGGARelaxMaker(
                        copy_vasp_kwargs={
                            "additional_vasp_files": ("WAVECAR", "CHGCAR")
                        }
                    ),
                    static_maker=MPMetaGGAStaticMaker(
                        copy_vasp_kwargs={
                            "additional_vasp_files": ("WAVECAR", "CHGCAR")
                        }
                    ),
                )

        return super().make(structure=structure, prev_dir=prev_dir)
