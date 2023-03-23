import numpy as np
import pandas as pd
import pickle
import matplotlib.pyplot as plt

import Folder
import Affichage
from Interface_Gmsh import Interface_Gmsh
from Geom import Point, Domain, Circle
import Materials
import Simulations
import PostTraitement

Affichage.Clear()

folder_file = Folder.Get_Path(__file__)

# ----------------------------------------------
# Config
# ----------------------------------------------

idxEssai = 1

folder_Save = Folder.Join([folder_file, "Identification_PFM"])

test = False
optimMesh = True

pltLoad = True
pltIter = True

# ----------------------------------------------
# Forces & Déplacements
# ----------------------------------------------

# récupère les courbes forces déplacements
# pathDataFrame = Folder.Join([folder_file, "data_dfEssais.pickle"])
pathDataFrame = Folder.Join([folder_file, "data_dfEssaisRedim.pickle"])
with open(pathDataFrame, "rb") as file:
    dfLoad = pd.DataFrame(pickle.load(file))
# print(dfLoad)

forces = dfLoad["forces"][idxEssai]
deplacements = dfLoad["deplacements"][idxEssai]

idx_fmax = np.argmax(forces)



# calcul de la pente pour connaitre le décrochage
idxElas = np.where((forces <= 15) & (deplacements<=deplacements[idx_fmax]))[0]
idx1, idx2 = idxElas[0], idxElas[-1]
x1, x2 = deplacements[idx1], deplacements[idx2]
f1, f2 = forces[idx1], forces[idx2]
vect_ab = np.linalg.inv(np.array([[x1, 1],[x2, 1]])).dot(np.array([f1, f2]))
a, b = vect_ab[0], vect_ab[1]

droiteElas = a * np.linspace(0, deplacements[idx_fmax], idx_fmax) + b

idxMax = np.where(droiteElas<=forces[idx_fmax])[0]

ecartDep = np.abs(forces[idxMax] - droiteElas[idxMax])/forces[idxMax]

# indexe permettant d'acceder au décrochage de la zone élastique
# idxDamage = np.where(ecartDep >= 3e-2)[0][0]
idxDamage = np.where(ecartDep >= 2e-2)[0][0]

if pltLoad:
    axLoad = plt.subplots()[1]
    axLoad.plot(deplacements, forces)
    axLoad.set_xlabel("displacement [kN]")
    axLoad.set_ylabel("load [mm]")

    axLoad.plot(deplacements[idxMax], droiteElas[idxMax])

    axLoad.scatter(deplacements[idxDamage], forces[idxDamage], marker='+', c='red')

# ----------------------------------------------
# Mesh
# ----------------------------------------------

h = 90
l = 45
b = 20
d = 10

l0 = l/50

meshSize = l0 if test else l0/3

if optimMesh:
    epRefine = d
    refineGeom = Domain(Point(l/2-epRefine), Point(l/2+epRefine, h), meshSize)
    meshSize *= 3
else:
    refineGeom = None

domain = Domain(Point(), Point(l, h), meshSize)
circle = Circle(Point(l/2, h/2), d, meshSize)

mesh = Interface_Gmsh(False).Mesh_Domain_Circle_2D(domain, circle, "TRI3", refineGeom)

nodes_Lower = mesh.Nodes_Tags(["L0"])
nodes_Upper = mesh.Nodes_Tags(["L2"])
nodes0 = mesh.Nodes_Tags(["P0"])
nodes_Boundary = mesh.Nodes_Tags(["L0", "L1", "L2", "L3"])

ddlsY = Simulations.BoundaryCondition.Get_ddls_noeuds(2, "displacement", nodes_Upper, ["y"])

Affichage.Plot_Mesh(mesh)
# Affichage.Plot_Model(mesh)

# ----------------------------------------------
# Comp and Simu
# ----------------------------------------------

# récupère les proritétés identifiées
pathParams = Folder.Join([folder_file, "params_Essais.xlsx"])

dfParams = pd.read_excel(pathParams)

# print(dfParams)

El = dfParams["El"][idxEssai]
Et = dfParams["Et"][idxEssai]
Gl = dfParams["Gl"][idxEssai]
# vl = dfParams["vl"][idxEssai]
vl = 0.02
vt = 0.44

axis_l = np.array([0,1,0])
axis_t = np.array([1,0,0])

comp = Materials.Elas_IsotTrans(2, El, Et, Gl, vl, vt, axis_l, axis_t, True, b)

Gc = 1e-2

a1 = np.array([1,0])
M1 = np.einsum("i,j->ij", a1, a1)

a2 = np.array([0,1])
M2 = np.einsum("i,j->ij", a2, a2)

# coef = El/Et
coef = Et/El
# A = np.eye(2)
# A = np.eye(2) + 0 * M1 + 0 * M2
# A = np.array([[coef, 0],[0, 1-coef]])
A = np.array([[coef, 0],[0, 1-coef]])

pfm = Materials.PhaseField_Model(comp, "AnisotStress", "AT1", Gc, l0, A=A)

simu = Simulations.Simu_PhaseField(mesh, pfm)

depMax = deplacements[idx_fmax]

inc0 = 1e-2
inc1 = inc0/2

dep = -inc0
i = -1
while dep <= depMax:

    i += 1
    dep += inc0 if simu.damage.max()<=0.5 else inc1

    simu.Bc_Init()
    simu.add_dirichlet(nodes_Lower, [0], ["y"])
    simu.add_dirichlet(nodes0, [0], ["x"])    
    simu.add_dirichlet(nodes_Upper, [-dep], ["y"])

    u, d, Kglob, convergence = simu.Solve(1e-0)

    simu.Resultats_Set_Resume_Iteration(i, dep, "mm", dep/depMax, True)

    simu.Save_Iteration()

    fr = - np.sum(Kglob[ddlsY] @ u)

    if pltLoad:
        plt.figure(axLoad.figure)
        axLoad.scatter(dep, fr/1000, c='black')
        plt.pause(1e-12)

    if pltIter:
        if i == 0:
            _, axIter, cbIter = Affichage.Plot_Result(simu, "damage")
        else:
            cbIter.remove()
            _, axIter, cbIter = Affichage.Plot_Result(simu, "damage", ax=axIter)
        plt.figure(axIter.figure)
        plt.pause(1e-12)

    if not convergence or True in (d[nodes_Boundary] >= 0.98):
        break


PostTraitement.Make_Paraview(folder_Save, simu)

 






plt.show()