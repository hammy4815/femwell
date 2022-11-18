import matplotlib.pyplot as plt
import numpy as np

from skfem import BilinearForm, Basis, ElementTriN1, ElementTriP0, ElementTriP1, Mesh, solve, FacetBasis, condense, \
    InteriorFacetBasis
from skfem.helpers import curl, grad, dot, inner


def compute_modes(basis, basis_epsilon_r, epsilon_r, wavelength, mu_r, source, D=None, x0=None):
    k0 = 2 * np.pi / wavelength
    one_over_u_r = 1 / mu_r

    @BilinearForm(dtype=np.complex64)
    def curl_form(Et, Ez, vt, vz, w):
        return one_over_u_r * inner(curl(Et), curl(vt)) + k0 ** 2 * w['epsilon'] * (inner(Et, vt)) \
               - one_over_u_r * (inner(grad(Ez), grad(vz))) + k0 ** 2 * w['epsilon'] * Ez * vz

    @BilinearForm(dtype=np.complex64)
    def div_form(Et, Ez, vt, vz, w):
        return dot(grad(Ez), vt) + dot(Et, grad(vz))

    A = curl_form.assemble(basis, epsilon=basis_epsilon_r.interpolate(epsilon_r))
    C = div_form.assemble(basis)

    if x0 is None:
        x = solve(A + C, source)
    else:
        x = solve(*condense(A + C, source, D=D, x=x0))

    return basis, x


if __name__ == '__main__':
    from collections import OrderedDict
    from shapely.geometry import Polygon, LineString
    from mesh import mesh_from_OrderedDict

    width = 4
    length = 10.5
    pml = .5

    width_wg_1 = .5
    length_wg_1 = 5
    extra_length_wg_1 = 1

    width_wg_2 = 2
    length_wg_2 = 5

    core = Polygon([
        (-width_wg_1 / 2, -length_wg_1),
        (-width_wg_1 / 2, 0),
        (-width_wg_2 / 2, 0),
        (-width_wg_2 / 2, length_wg_2),
        (width_wg_2 / 2, length_wg_2),
        (width_wg_2 / 2, 0),
        (width_wg_1 / 2, 0),
        (width_wg_1 / 2, -length_wg_1),
    ])
    core_append = Polygon([
        (-width_wg_1 / 2, -length_wg_1),
        (-width_wg_1 / 2, -length_wg_1 - extra_length_wg_1),
        (width_wg_1 / 2, -length_wg_1 - extra_length_wg_1),
        (width_wg_1 / 2, -length_wg_1),
    ])

    source = LineString([
        (width_wg_2 / 2, -length_wg_1 / 2),
        (-width_wg_2 / 2, -length_wg_1 / 2)
    ])

    polygons = OrderedDict(
        source=source,
        core=core,
        core_append=core_append,
        box=core.buffer(1, resolution=4) - core,
        pml=core.buffer(2, resolution=4) - core.buffer(1, resolution=4),
    )

    resolutions = dict(
        core={"resolution": .05, "distance": 1},
        core_append={"resolution": .05, "distance": 1},
        box={"resolution": .05, "distance": 1},
    )

    mesh = mesh_from_OrderedDict(polygons, resolutions, filename='mesh.msh', default_resolution_max=.3)
    mesh = Mesh.load('mesh.msh')

    basis = Basis(mesh, ElementTriN1() * ElementTriP1())

    basis0 = basis.with_element(ElementTriP0())
    epsilon = basis0.zeros(dtype=complex) + 1.444 ** 2
    epsilon[basis0.get_dofs(elements='core')] = 2.8 ** 2
    epsilon[basis0.get_dofs(elements='core_append')] = 2.8 ** 2
    epsilon[basis0.get_dofs(elements='pml')] = (1.444 + 1j) ** 2
    basis0.plot(np.real(epsilon)).show()

    basis0_source = FacetBasis(mesh, basis0.elem, facets=mesh.boundaries['source'], intorder=4)
    basis_source = FacetBasis(mesh, basis.elem, facets=mesh.boundaries['source'], intorder=4)

    # source = basis_source.project(
    #    lambda x: [np.array([0 + 0 * x[0], 0 * np.exp(0 * x[0] ** 2) + 0 * x[0]]), 1 + 0 * x[0]])
    # source = source.astype(complex)
    # source *= 1j

    basis_source_1d = basis_source.with_element(ElementTriP1())

    wavelength = 1.55
    k0 = 2 * np.pi / wavelength


    @BilinearForm
    def lhs(u, v, w):
        return -1 / k0 ** 2 * inner(grad(u)[0], grad(v)[0]) + w['epsilon'] * inner(u, v)


    @BilinearForm
    def rhs(u, v, w):
        return inner(u, v)

    A = lhs.assemble(basis_source_1d, epsilon=basis0_source.interpolate(epsilon))
    B = rhs.assemble(basis_source_1d)

    from skfem.utils import solver_eigen_scipy_sym

    lams, xs = solve(*condense(A, B, I=basis_source_1d.get_dofs(facets='source')),
                     solver=solver_eigen_scipy_sym(sigma=3.55 ** 2, which='LM'))
    print(np.sqrt(lams))

    # xs[:,0] = xs[:,0]*0+1
    x0 = basis_source.project((np.array((basis_source_1d.interpolate(0*xs[:,-1]), basis_source_1d.interpolate(xs[:,-1]))), basis_source_1d.interpolate(0*xs[:,-1])))

    basis, x = compute_modes(basis, basis0, epsilon, 1.55, 1, basis.zeros(), D=basis_source.get_dofs(facets='source'),
                             x0=x0)

    from mode_solver import plot_mode

    plot_mode(basis, np.real(x), direction='x')
    plt.show()
    plot_mode(basis, np.imag(x), direction='x')
    plt.show()
