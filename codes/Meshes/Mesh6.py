import Display
from Interface_Gmsh import Interface_Gmsh, GroupElem, ElemType
from Geom import Point, Line, Circle, PointsList, Domain, Contour
import Materials
import Simulations

Display.Clear()

L = 1
meshSize = L/5

contour = Domain(Point(), Point(L, L), meshSize)
circle = Circle(Point(L/2,L/2), L/3, meshSize)
inclusions = [circle]

refine1 = Domain(Point(0, L), Point(L, L*0.8), meshSize/8)
refine2 = Circle(circle.center, L/2, meshSize/8)
refine3 = Circle(Point(), L/2, meshSize/8)
refineGeoms = [refine1, refine2, refine3]

def DoMesh(dim, elemType):
    if dim == 2:
        mesh = Interface_Gmsh().Mesh_2D(contour, inclusions, elemType, refineGeoms=refineGeoms)
    elif dim == 3:
        mesh = Interface_Gmsh().Mesh_3D(contour, inclusions, [0, 0, -L], 3, elemType, refineGeoms=refineGeoms)

    # checks that the system is correctly assembled
    material = Materials.Elas_Isot(dim)
    simu = Simulations.Simu_Displacement(mesh, material)
    simu.Assembly()

    Display.Plot_Mesh(mesh)

[DoMesh(2, elemType) for elemType in GroupElem.get_Types2D()]

[DoMesh(3, elemType) for elemType in GroupElem.get_Types3D()]

Display.plt.show()