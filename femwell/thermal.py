from typing import Dict
from collections import OrderedDict

import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import Polygon

from skfem import asm, ElementTriP0, ElementTriP1, BilinearForm, LinearForm, Basis, solve, condense, Mesh
from skfem.helpers import dot

from femwell.mesh import mesh_from_polygons


def solve_thermal(
        basis0,
        thermal_conductivity,
        specific_conductivity: Dict[str, float],
        current_densities,
        fixed_boundaries
):
    """Thermal simulation.

    Args:
        basis0: Basis of the thermal_conductivity
        thermal_conductivity: thermal conductivity in W/m‧K.
        specific_conductivity: specific conductivity in S/m.
        current_densities: current densities flowing through the layer in A.

    Returns:
        basis, temperature profile
    """

    @BilinearForm
    def conduction(u, v, w):
        return dot(w["thermal_conductivity"] * u.grad, v.grad)

    basis = basis0.with_element(ElementTriP1())

    @LinearForm
    def unit_load(v, _):
        return v

    joule_heating_rhs = basis.zeros()
    for domain, current_density in current_densities.items():  # sum up the sources for the heating
        core_basis = Basis(basis.mesh, basis.elem, elements=basis.mesh.subdomains[domain])
        joule_heating_rhs += current_density ** 2 / specific_conductivity[domain] * unit_load.assemble(core_basis)

    thermal_conductivity_lhs = asm(
        conduction,
        basis,
        thermal_conductivity=basis0.interpolate(thermal_conductivity),
    )
    print(fixed_boundaries.keys())
    x = basis.zeros()
    for key, value in fixed_boundaries.items():
        x[basis.get_dofs(key)] = value

    temperature = solve(
        *condense(
            thermal_conductivity_lhs,
            joule_heating_rhs,
            D={fixed_boundary: basis.get_dofs(fixed_boundary) for fixed_boundary in fixed_boundaries},
            x=x
        )
    )

    return basis, temperature


if __name__ == '__main__':
    # Simulating the TiN TOPS heater in https://doi.org/10.1364/OE.27.010456

    w_sim = 8 * 2
    h_clad = 2.8
    h_box = 1
    w_core = 0.5
    h_core = 0.22
    offset_heater = 2.2
    h_heater = .14
    w_heater = 2

    polygons = OrderedDict(
        core=Polygon([
            (-w_core / 2, -h_core / 2),
            (-w_core / 2, h_core / 2),
            (w_core / 2, h_core / 2),
            (w_core / 2, -h_core / 2),
        ]),
        heater=Polygon([
            (-w_heater / 2, -h_heater / 2 + offset_heater),
            (-w_heater / 2, h_heater / 2 + offset_heater),
            (w_heater / 2, h_heater / 2 + offset_heater),
            (w_heater / 2, -h_heater / 2 + offset_heater),
        ]),
        clad=Polygon([
            (-w_sim / 2, -h_core / 2),
            (-w_sim / 2, -h_core / 2 + h_clad),
            (w_sim / 2, -h_core / 2 + h_clad),
            (w_sim / 2, -h_core / 2),
        ]),
        box=Polygon([
            (-w_sim / 2, -h_core / 2),
            (-w_sim / 2, -h_core / 2 - h_box),
            (w_sim / 2, -h_core / 2 - h_box),
            (w_sim / 2, -h_core / 2),
        ])
    )

    resolutions = dict(
        core={"resolution": 0.02, "distance": 1},
        clad={"resolution": 0.4, "distance": 1},
        box={"resolution": 0.4, "distance": 1},
        heater={"resolution": 0.05, "distance": 1}
    )

    mesh_from_polygons(polygons, resolutions, filename='mesh.msh', default_resolution_max=.4)

    mesh = Mesh.load('mesh.msh')

    currents = np.linspace(0.007, 10e-3, 10) / polygons['heater'].area
    neffs = []

    from tqdm.auto import tqdm

    for current in tqdm(currents):
        basis0 = Basis(mesh, ElementTriP0(), intorder=4)
        thermal_conductivity_p0 = basis0.zeros()
        for domain, value in {"core": 148, "box": 1.38, "clad": 1.38, "heater": 28}.items():
            thermal_conductivity_p0[basis0.get_dofs(elements=domain)] = value
        thermal_conductivity_p0 *= 1e-12  # 1e-12 -> conversion from 1/m^2 -> 1/um^2

        basis, temperature = solve_thermal(basis0, thermal_conductivity_p0,
                                           specific_conductivity={"heater": 2.3e6},
                                           current_densities={"heater": current},
                                           fixed_boundaries={'box_None_14': 0})
        # basis.plot(temperature, colorbar=True)
        # plt.show()

        from femwell.mode_solver import compute_modes, plot_mode

        temperature0 = basis0.project(basis.interpolate(temperature))
        epsilon = basis0.zeros() + (1.444 + 1.00e-5 * temperature0) ** 2
        epsilon[basis0.get_dofs(elements='core')] = \
            (3.4777 + 1.86e-4 * temperature0[basis0.get_dofs(elements='core')]) ** 2
        # basis0.plot(epsilon, colorbar=True).show()

        lams, basis, xs = compute_modes(basis0, epsilon, wavelength=1.55, mu_r=1, num_modes=5)

        print(lams)

        # plot_mode(basis, xs[0])
        # plt.show()

        neffs.append(np.real(lams[0]))

    print(f'Phase shift: {2 * np.pi / 1.55 * (neffs[-1] - neffs[0]) * 320}')
    plt.plot(currents, neffs)
    plt.show()