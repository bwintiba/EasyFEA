from Simu import Simu
import numpy as np
import scipy.sparse as sp
import Dossier

def ResolutionIteration(simu: Simu, tolConv=1, maxIter=200) -> tuple[np.ndarray, np.ndarray, sp.csr_matrix, int]:
    """Calcul l'itération d'un probleme d'endommagement de façon étagée

    Parameters
    ----------
    simu : Simu
        simulation
    tolConv : float, optional
        tolérance de convergence entre l'ancien et le nouvelle endommagement, by default 1.0
    maxIter : int, optional
        nombre d'itération maximum pour atteindre la convergence, by default 200

    Returns
    -------
    np.ndarray, np.ndarray, int
        u, d, Kglob, iterConv\n

        tel que :\n
        u : champ vectorielle de déplacement
        d : champ scalaire d'endommagement
        Kglob : matrice de rigidité en déplacement
        iterConv : iteration nécessaire pour atteindre la convergence
    """

    assert tolConv > 0 and tolConv <= 1 , "tolConv doit être compris entre 0 et 1"
    assert maxIter > 1 , "Doit être > 1"

    iterConv=0
    convergence = False
    d = simu.damage

    while not convergence:
                
        iterConv += 1
        dold = d.copy()

        # Damage
        simu.Assemblage_d()
        d = simu.Solve_d()

        # Displacement
        Kglob = simu.Assemblage_u()            
        u = simu.Solve_u()

        dincMax = np.max(np.abs(d-dold))
        convergence = dincMax <= tolConv
        # if damage.min()>1e-5:
        #     convergence=False

        if iterConv == maxIter:
            break
        
        if tolConv == 1.0:
            convergence=True
        
    return u, d, Kglob, iterConv

def AffichageIteration(resol: int, dep: float, d: np.ndarray, iterConv: int, temps: float, uniteDep="m", pourcentage=0, remove=False):
    min_d = d.min()
    max_d = d.max()
    texte = f"{resol:4} : ud = {np.round(dep,3)} {uniteDep},  d = [{min_d:.2e}; {max_d:.2e}], {iterConv}:{np.round(temps,3)} s  "
    
    if remove:
        end='\r'
    else:
        end=''

    if pourcentage > 0:
        texte = f"{np.round(pourcentage*100,2)} % " + texte
    
    print(texte, end=end)

def ConstruitDossier(dossierSource: str, comp: str, split: str, regu: str, simpli2D: str, tolConv: float,
useHistory: bool, test: bool, openCrack:bool, v=0):

    nom="_".join([comp, split, regu, simpli2D])

    if openCrack: 
        nom += '_openCrack'

    if tolConv < 1:
        nom += f'_convergence{tolConv}'
    
    if not useHistory:
        nom += '_noHistory'

    if comp == "Elas_Isot" and v != 0:
        nom = f"{nom} pour v={v}"

    folder = Dossier.NewFile(dossierSource, results=True)

    if test:
        folder = Dossier.Join([folder, "Test", nom])
    else:
        folder = Dossier.Join([folder, nom])

    return folder