# Frictionless contact assumption
# WARNING : the assumption of small displacements is more than questionable for this simulation

import Display
from Interface_Gmsh import Interface_Gmsh, ElemType, Mesh
from Geom import Point, Domain, Circle, PointsList, Geom
from Mesh import Get_new_mesh
import Materials
import Simulations

plt = Display.plt
np = Display.np

Display.Clear()

# --------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------
dim = 2

R = 10
height = R
meshSize = R/20
thickness = R/3

N = 30

# displacements = np.ones(N) * 1e-0/N
# cx, cy = 0, -1
# dec = [0, 0]

displacements = np.ones(N) * 2*R/N
cx, cy = 1, 0
dec = [R, 2]

# dep = [cx, cy] * ud

# --------------------------------------------------------------------------------------------
# Meshes
# --------------------------------------------------------------------------------------------

# slave mesh
contour_slave = Domain(Point(-R/2,0), Point(R/2,height), meshSize)
if dim == 2:
    mesh_slave = Interface_Gmsh().Mesh_2D(contour_slave, [], ElemType.QUAD4, isOrganised=True)
else:
    mesh_slave = Interface_Gmsh().Mesh_3D(contour_slave, [], [0,0,-thickness], 4, ElemType.PRISM6, isOrganised=True)

nodes_slave = mesh_slave.Get_list_groupElem(dim-1)[0].nodes
nodes_y0 = mesh_slave.Nodes_Conditions(lambda x,y,z: y==0)

# master mesh
if dim == 3: dec.append(-1)    
r = R/2
p0 = Point(-R/2, height, r=r) - dec 
p1 = Point(R/2, height, r=r) - dec 
p2 = Point(R/2, height+R) - dec 
p3 = Point(-R/2, height+R) - dec 
contour_master = PointsList([p0,p1,p2,p3], meshSize*2)
yMax = height+np.abs(r)
if dim == 2:
    mesh_master = Interface_Gmsh().Mesh_2D(contour_master, [], ElemType.TRI3)
else:    
    mesh_master = Interface_Gmsh().Mesh_3D(contour_master, [], [0,0,-thickness-2], 4, ElemType.PRISM6)

# get master nodes
nodes_master = mesh_master.Get_list_groupElem(dim-1)[0].nodes

# plot meshes
ax = Display.Plot_Mesh(mesh_master, alpha=0)
Display.Plot_Mesh(mesh_slave, ax=ax, alpha=0)
# add nodes interface
ax.scatter(*mesh_slave.coordo[nodes_slave,:dim].T, label='slave nodes')
ax.scatter(*mesh_master.coordo[nodes_master,:dim].T, label='master nodes')
ax.legend()
ax.set_title('Contact nodes')

# --------------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------------
material = Materials.Elas_Isot(dim, E=210000, v=0.3, planeStress=True, thickness=thickness)
simu = Simulations.Simu_Displacement(mesh_slave, material)

list_mesh_master = [mesh_master]

fig, ax, cb = Display.Plot_Result(simu, 'uy', deformFactor=1)

for i, ud in enumerate(displacements):

    # create the new master mesh
    displacementMatrix = np.zeros((mesh_master.Nn, 3))    
    displacementMatrix[:,0] = cx * ud
    displacementMatrix[:,1] = cy * ud
    mesh_master = Get_new_mesh(mesh_master, displacementMatrix)
    list_mesh_master.append(mesh_master)

    groupMaster = mesh_master.Get_list_groupElem(dim-1)[0]
    if dim == 3 and i == 0 and len(mesh_master.Get_list_groupElem(dim-1)) > 1:
        print(f"The {groupMaster.elemType.name} element group is used. In 3D, TETRA AND HEXA elements are recommended.")

    convergence=False

    coordo_old = simu.Results_displacement_matrix() + simu.mesh.coordo

    while not convergence:

        # apply new boundary conditions
        simu.Bc_Init()
        simu.add_dirichlet(nodes_y0, [0]*dim, simu.Get_directions())

        nodes, newU = simu.Get_contact(mesh_master, nodes_slave)

        if nodes.size > 0:        
            simu.add_dirichlet(nodes, [newU[:,0], newU[:,1]], ['x','y'])

        simu.Solve()

        # check if there is no new nodes in the master mesh
        oldSize = nodes.size
        nodes, _ = simu.Get_contact(mesh_master, nodes_slave)

        convergence = oldSize == nodes.size

    simu.Save_Iter()

    print(f"Eps max = {simu.Get_Result('Strain').max()*100:3.2f} %")
    
    ax.clear()
    cb.remove()
    _,ax,cb = Display.Plot_Result(simu, 'uy', plotMesh=True, deformFactor=1, ax=ax)
    Display.Plot_Mesh(mesh_master, alpha=0, ax=ax)
    ax.set_title('uy')
    if dim == 3:
        Display._ScaleChange(ax, np.concatenate((mesh_master.coordo, mesh_slave.coordo), 0))
    
    # # Plot arrows
    # if nodes.size >0:
    #     # get the nodes coordinates on the interface
    #     coordinates = groupMaster.Get_GaussCoordinates_e_p('mass').reshape(-1,3)
    #     ax.scatter(*coordinates[:,:dim].T)

    #     coordo_new = simu.Results_displacement_matrix() + simu.mesh.coordo
    #     ax.scatter(*coordo_old[nodes,:dim].T)
    #     if dim == 2:
    #         incU = coordo_new - coordo_old
    #         [ax.arrow(*coordo_old[node, :2], incU[node,0], incU[node,1],length_includes_head=True) for node in nodes]
    # # ax.set_xlim(xmin=-R/4, xmax=R/4)
    # # ax.set_ylim(ymin=height-ud-height/10, ymax=height-ud+height/10)

    plt.pause(1e-12)
    
    pass

# --------------------------------------------------------------------------------------------
# PostProcessing
# --------------------------------------------------------------------------------------------
Display.Plot_Result(simu, 'Eyy', nodeValues=True)
Display.Plot_Result(simu, 'ux')
Display.Plot_Result(simu, 'uy')

Simulations.Tic.Plot_History(details=True)

# import Folder
# import PostProcessing
# folder = Folder.New_File('Contact', results=True)
# PostProcessing.Make_Paraview(folder, simu)
# # TODO how to plot the two meshes ?
# TODO bending 3 pts

print(simu)

plt.show()