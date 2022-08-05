import PostTraitement
import Affichage
import Dossier
import numpy as np
import matplotlib.pyplot as plt
import TicTac

# L'objectif du script est de récupérer pour chaque simulation la courbe force déplacement
# Didentifier 3 itérations de déplacement (18.5, 24.6, 30) µm 
# Pour ces 3 itérations tracer endommagement

Affichage.Clear()

test=False

comp = "Elas_Isot" # ["Elas_Isot", "Elas_IsotTrans"]
regu = "AT1" # "AT1", "AT2"
simpli2D = "DP" # ["CP","DP"]
useHistory=True

# Convergence
maxIter = 250
# tolConv = 0.01
tolConv = 1

plotDamage = False

v=0.3

snapshot = [18.5, 24.6, 28]

nomDossier = "PlateWithHole_Benchmark"
folder = Dossier.NewFile(nomDossier, results=True)

if test:
    folderSauvegarde = Dossier.Join([folder, "Test", "_Post traitement"])
else:
    folderSauvegarde = Dossier.Join([folder, "_Post traitement"])

fig, ax = plt.subplots()

# ,"AnisotMiehe","AnisotMiehe_NoCross","AnisotStress","AnisotStress_NoCross"
for split in ["Bourdin","Amor","Miehe"]: #["Bourdin","Amor","Miehe","He","Stress"]

    tic = TicTac.TicTac()

    # Récupère le nom du dossier
    nom="_".join([comp, split, regu, simpli2D])

    if tolConv < 1:
        testConvergence = True
        nom += f'_convergence{tolConv}'
    else:
        testConvergence = False
    
    if not useHistory:
        nom += '_noHistory'

    if comp == "Elas_Isot":
        nom = f"{nom} pour v={v}"

    

    folder = Dossier.NewFile(nomDossier, results=True)

    if test:
        folder = Dossier.Join([folder, "Test", nom])
    else:
        folder = Dossier.Join([folder, nom])

    # Charge la simulation
    simu = PostTraitement.Load_Simu(folder, False)

    # Charge la force et le déplacement
    load, displacement = PostTraitement.Load_Load_Displacement(folder, False)

    if plotDamage:
        # Affiche le dernier endommagement
        Affichage.Plot_Result(simu, "damage", valeursAuxNoeuds=True, colorbarIsClose=True,
        folder=folderSauvegarde, filename=f"{nom} last", 
        title=r"$\phi$")
        

        # Récupère les itérations à 18.5, 24.6, 30 et trace l'endommagement
        for dep in snapshot:
            try:
                i = np.where(np.abs(displacement*1e6-dep)<1e-12)[0][0]
            except:
                # i n'a pas été trouvé on continue les iterations
                continue
            
            simu.Update_iter(i)

            filenameDamage = f"{nom} et ud = {np.round(displacement[i]*1e6,2)}"

            Affichage.Plot_Result(simu, "damage", valeursAuxNoeuds=True, colorbarIsClose=True,
            folder=folderSauvegarde, filename=filenameDamage, 
            title=fr"${split}$")

    # texte = nom.replace(f" pour v={v}", "")
    texte = split

    indexLim = np.where(displacement*1e6 <= 26)[0]
    ax.plot(displacement[indexLim]*1e6, np.abs(load[indexLim]*1e-6), label=texte)

    # ax.plot(displacement*1e6, np.abs(load*1e-6), label=texte)

    tic.Tac("Post traitement", split, True)

ax.set_xlabel("displacement [µm]")
ax.set_ylabel("load [kN]")
ax.grid()
ax.legend()
plt.figure(fig)
PostTraitement.Save_fig(folderSauvegarde, "load displacement")

plt.show()
        


    