from types import LambdaType
from typing import List, cast, Dict

import numpy as np
from scipy import sparse

import Affichage as Affichage
from Mesh import Mesh
from BoundaryCondition import BoundaryCondition, LagrangeCondition
from Materials import *
from TicTac import Tic
import CalcNumba
import Interface_Solveurs


class Simu:

# ------------------------------------------- CONSTRUCTEUR ------------------------------------------- 

    @staticmethod
    def CheckProblemTypes(problemType:str):
        """Verifie si ce type de probleme est implénté"""
        list_problemType = ["displacement", "damage", "thermal", "beam"]
        assert problemType in list_problemType, "Ce type de probleme n'est pas implémenté"

    def __Check_Autorisation(self, listProblemType: List[str]) -> bool:
        """Verifie si la simulation peut utiliser le type de problème renseigné"""
        
        autorisation = False
        
        for problemType in listProblemType:
            if problemType == self.__problemType:
                autorisation = True

        if not autorisation:
            print(f"La simulation n'est pas une simulation {problemType} mais une simulation {self.__problemType}")
            # TODO Ici il pourrait être intéressant de proposer un conseil ?

        return autorisation

    def __init__(self, mesh: Mesh, materiau: Materiau, verbosity=True, useNumba=True):
        """Creation d'une simulation

        Args:
            dim (int): Dimension de la simulation (2D ou 3D)
            mesh (Mesh): Maillage que la simulation va utiliser
            materiau (Materiau): Materiau utilisé
            verbosity (bool, optional): La simulation ecrira dans la console. Defaults to True.
        """

        if verbosity:
            Affichage.NouvelleSection("Simulation")

        dim = mesh.dim

        # Vérification des valeurs
        if isinstance(materiau.beamModel, BeamModel):
            dim = materiau.dim
        else:
            assert materiau.dim == dim, "Doit avoir la meme dimension que dim"

        self.__dim = dim
        """dimension de la simulation 2D ou 3D"""
        self.__verbosity = verbosity
        """la simulation peut ecrire dans la console"""

        self.__mesh = mesh
        """maillage de la simulation"""
        self.materiau = materiau
        """materiau de la simulation"""

        Simu.CheckProblemTypes(materiau.problemType)
        self.__problemType = materiau.problemType

        if materiau.isDamaged:
            materiau.phaseFieldModel.useNumba = useNumba
            
        self.__useNumba = useNumba
        # if useNumba:
        #     CalcNumba.CompilNumba(self.__verbosity)
        
        # resultats
        self.__init_results()

        # Conditions Limites
        self.Init_Bc()

# ------------------------------------------- FONCTIONS ------------------------------------------- 

    # TODO Permettre de creer des simulation depuis le formulation variationnelle ?

    @property
    def problemType(self) -> str:
        return self.materiau.problemType
    
    @property
    def mesh(self) -> Mesh:
        """maillage de la simulation"""
        return self.__mesh

    @property
    def dim(self) -> int:
        """dimension de la simulation"""
        return self.__dim

# ------------------------------------------- RESULTATS ------------------------------------------- 

    def __init_results(self):
        """Construit les arrays qui vont stocker les resultats et initialise le tabeau de résultat"""

        if self.__problemType == "thermal":
            self.__thermal = np.zeros(self.__mesh.Nn)

            if self.materiau.thermalModel.c > 0 and self.materiau.ro > 0:
                # Il est possible de calculer la matrice de masse et donc de résoudre un problème parabolic au lieu d'elliptic
                self.__thermalDot = np.zeros_like(self.__thermal)

        elif self.__problemType == "displacement":
            self.__displacement = np.zeros(self.__mesh.Nn*self.__dim)

            if self.materiau.ro > 0:
                self.Set_Rayleigh_Damping_Coefs()
                self.__speed = np.zeros_like(self.__displacement)                
                self.__accel = np.zeros_like(self.__displacement)

        elif self.__problemType == "beam":
            self.__beamDisplacement = np.zeros(self.__mesh.Nn*self.materiau.beamModel.nbddl_n)
        
        elif self.__problemType == "damage":
            self.__displacement = np.zeros(self.__mesh.Nn*self.__dim)
            self.__damage = np.zeros(self.__mesh.Nn)
            self.__psiP_e_pg = []
            self.__old_psiP_e_pg = [] #ancienne densitée d'energie elastique positive PsiPlus(e, pg, 1) pour utiliser le champ d'histoire de miehe
        else:
            raise "probleme inconnue"
            
        self.resumeChargement = "" #resumé du chargement

        self.resumeIter = "" #resumé de l'iteration

        self.__results = [] #liste de dictionnaire qui contient les résultats

        self.Set_Parabolic_AlgoProperties() # Renseigne les propriétes de résolution de l'algorithme
        self.Set_Hyperbolic_AlgoProperties() # Renseigne les propriétes de résolution de l'algorithme
        # self.Save_Iteration()

    @property
    def damage(self) -> np.ndarray:
        """Copie du champ scalaire d'endommagement"""
        if self.__problemType == "damage":
            return self.__damage.copy()
        else:
            return None

    @property
    def thermal(self) -> np.ndarray:
        """Copie du champ scalaire de température"""
        if self.__problemType == "thermal":
            return self.__thermal.copy()
        else:
            return None

    @property
    def thermalDot(self) -> np.ndarray:
        """Copie de la dérivée du champ scalaire de température"""
        if self.__problemType == "thermal" and self.materiau.thermalModel.c > 0 and self.materiau.ro > 0:
            return self.__thermalDot.copy()
        else:
            return None
    
    @property
    def displacement(self) -> np.ndarray:
        """Copie du champ vectoriel de déplacement"""
        if self.__problemType in ["displacement", "damage"]:
            return self.__displacement.copy()
        else:
            return None

    @property
    def beamDisplacement(self) -> np.ndarray:
        """Copie du champ vectoriel de déplacement pour le problème poutre"""
        if self.__problemType == "beam":
            return self.__beamDisplacement.copy()
        else:
            return None

    @property
    def speed(self) -> np.ndarray:
        """Copie du champ vectoriel de vitesse"""
        if self.__problemType in ["displacement", "damage"] and self.materiau.ro:
            return self.__speed.copy()
        else:
            return None
    
    @property
    def accel(self) -> np.ndarray:
        """Copie du champ vectoriel d'accéleration"""
        if self.__problemType in ["displacement", "damage"] and self.materiau.ro:
            return self.__accel.copy()
        else:
            return None

    def Get_Results_Index(self, index=None):
        """Recupère le resultat stocké dans la liste de dictionnaire"""
        if index == None:
            return self.__results[-1]
        else:
            return self.__results[index]

    @property
    def results(self) -> List[dict]:
        """Renvoie la liste de dictionnaire qui stocke les résultats
        """
        return self.__results

    def Save_Iteration(self, nombreIter=None, tempsIter=None, dincMax=None):
        """Sauvegarde les résultats de l'itération"""

        problemType = self.__problemType

        if problemType == "thermal":
            iter = {                
                'thermal' : self.__thermal
            }
            try:
                iter['thermalDot'] = self.__thermalDot                
            except:
                # Résultat non disponible
                pass

        elif problemType == "displacement":
            iter = {                
                'displacement' : self.__displacement
            }
        
        elif problemType == "damage":
            if self.materiau.phaseFieldModel.solveur == "History":
                # mets à jour l'ancien champ histoire pour la prochaine résolution 
                self.__old_psiP_e_pg = self.__psiP_e_pg
                
            iter = {                
                'displacement' : self.__displacement,
                'damage' : self.__damage
            }

        if nombreIter != None and tempsIter != None and dincMax != None:
            iter["nombreIter"] = nombreIter
            iter["tempsIter"] = tempsIter
            iter["dincMax"] = dincMax

        # TODO Faire de l'adaptation de maillage ?
        self.__results.append(iter)

    def Update_iter(self, iter: int):
        """Met la simulation à literation renseignée"""
        iter = int(iter)
        assert isinstance(iter, int), "Doit fournir un entier"

        # On va venir récupérer les resultats stocké dans le tableau pandas
        results = self.Get_Results_Index(iter)

        problemType = self.__problemType

        if problemType == "thermal":
            self.__thermal = results["thermal"]
            try:
                self.__thermalDot = results["thermalDot"]
            except:
                # Résultat non disponible
                pass

        elif problemType == "displacement":
            self.__displacement = results["displacement"]
        elif problemType == "damage":
            self.__old_psiP_e_pg = [] # TODO est il vraiment utile de faire ça ?
            self.__damage = results["damage"]
            self.__displacement = results["displacement"]

# ------------------------------------------- PROBLEME EN DEPLACEMENT ------------------------------------------- 

    def ConstruitMatElem_Dep(self, steadyState=True) -> np.ndarray:
        """Construit les matrices de rigidités élementaires pour le problème en déplacement

        Returns:
            dict_Ku_e: les matrices elementaires pour chaque groupe d'element
        """

        if not self.__Check_Autorisation(["displacement","damage"]): return

        useNumba = self.__useNumba
        # useNumba = False
        
        isDamaged = self.materiau.isDamaged

        matriceType="rigi"

        # Data
        mesh = self.__mesh
        nPg = mesh.Get_nPg(matriceType)
        
        # Recupère les matrices pour travailler
        
        B_dep_e_pg = mesh.Get_B_dep_e_pg(matriceType)
        leftDepPart = mesh.Get_leftDepPart(matriceType) # -> jacobien_e_pg * poid_pg * B_dep_e_pg'

        comportement = self.materiau.comportement

        if isDamaged:   # probleme endomagement

            d = self.__damage
            u = self.__displacement

            phaseFieldModel = self.materiau.phaseFieldModel
            
            # Calcul la deformation nécessaire pour le split
            Epsilon_e_pg = self.__Calc_Epsilon_e_pg(u, matriceType)

            # Split de la loi de comportement
            cP_e_pg, cM_e_pg = phaseFieldModel.Calc_C(Epsilon_e_pg)

            tic = Tic()
            
            # Endommage : c = g(d) * cP + cM
            g_e_pg = phaseFieldModel.get_g_e_pg(d, mesh, matriceType)
            useNumba=False
            if useNumba:
                # Moins rapide
                cP_e_pg = CalcNumba.ep_epij_to_epij(g_e_pg, cP_e_pg)
                # testcP_e_pg = np.einsum('ep,epij->epij', g_e_pg, cP_e_pg, optimize='optimal') - cP_e_pg
            else:
                # Plus rapide
                cP_e_pg = np.einsum('ep,epij->epij', g_e_pg, cP_e_pg, optimize='optimal')

            c_e_pg = cP_e_pg+cM_e_pg
            
            # Matrice de rigidité élementaire
            useNumba = self.__useNumba
            if useNumba:
                # Plus rapide
                Ku_e = CalcNumba.epij_epjk_epkl_to_eil(leftDepPart, c_e_pg, B_dep_e_pg)
            else:
                # Ku_e = np.einsum('ep,p,epki,epkl,eplj->eij', jacobien_e_pg, poid_pg, B_dep_e_pg, c_e_pg, B_dep_e_pg, optimize='optimal')
                Ku_e = np.einsum('epij,epjk,epkl->eil', leftDepPart, c_e_pg, B_dep_e_pg, optimize='optimal') 
            
        else:   # probleme en déplacement simple

            tic = Tic()

            # Ici on le materiau est homogène
            matC = comportement.get_C()

            if useNumba:
                # Plus rapide
                Ku_e = CalcNumba.epij_jk_epkl_to_eil(leftDepPart, matC, B_dep_e_pg)
            else:
                # Ku_e = np.einsum('ep,p,epki,kl,eplj->eij', jacobien_e_pg, poid_pg, B_dep_e_pg, matC, B_dep_e_pg, optimize='optimal')
                Ku_e = np.einsum('epij,jk,epkl->eil', leftDepPart, matC, B_dep_e_pg, optimize='optimal')
        
        if not steadyState:
            jacobien_e_pg = mesh.Get_jacobien_e_pg(matriceType)
            poid_pg = mesh.Get_poid_pg(matriceType)
            N_vecteur_e_pg = mesh.Get_N_vecteur_pg(matriceType)
            ro = self.materiau.ro

            Mu_e = np.einsum('ep,p,pki,,pkj->eij', jacobien_e_pg, poid_pg, N_vecteur_e_pg, ro, N_vecteur_e_pg, optimize="optimal")

        if self.__dim == 2:
            epaisseur = self.materiau.epaisseur
            Ku_e *= epaisseur
            if not steadyState:
                Mu_e *= epaisseur
        
        tic.Tac("Matrices","Construction Ku_e", self.__verbosity)

        if steadyState:
            return Ku_e
        else:
            return Ku_e, Mu_e
 
    def Assemblage_u(self, steadyState=True):
        """Construit K global pour le problème en deplacement
        """

        if not self.__Check_Autorisation(["displacement","damage"]): return

        # Data
        mesh = self.__mesh        
        taille = mesh.Nn*self.__dim

        # Construit dict_Ku_e
        if steadyState:
            Ku_e = self.ConstruitMatElem_Dep(steadyState)
        else:
            Ku_e, Mu_e = self.ConstruitMatElem_Dep(steadyState)

        # Prépare assemblage
        lignesVector_e = mesh.lignesVector_e
        colonnesVector_e = mesh.colonnesVector_e
        
        tic = Tic()

        # Assemblage
        self.__Ku = sparse.csr_matrix((Ku_e.reshape(-1), (lignesVector_e.reshape(-1), colonnesVector_e.reshape(-1))), shape=(taille, taille))
        """Matrice Kglob pour le problème en déplacement (Nn*dim, Nn*dim)"""

        # Ici j'initialise Fu calr il faudrait calculer les forces volumiques dans __ConstruitMatElem_Dep !!!
        self.__Fu = sparse.csr_matrix((taille, 1))
        """Vecteur Fglob pour le problème en déplacement (Nn*dim, 1)"""

        # import matplotlib.pyplot as plt
        # plt.figure()
        # plt.spy(self.__Ku)
        # plt.show()

        if steadyState:
            tic.Tac("Matrices","Assemblage Ku et Fu", self.__verbosity)
            return self.__Ku
        else:
            self.__Mu = sparse.csr_matrix((Mu_e.reshape(-1), (lignesVector_e.reshape(-1), colonnesVector_e.reshape(-1))), shape=(taille, taille))
            """Matrice Mglob pour le problème en déplacement (Nn*dim, Nn*dim)"""

            tic.Tac("Matrices","Assemblage Ku, Mu et Fu", self.__verbosity)
            return self.__Ku, self.__Mu

    def Set_Rayleigh_Damping_Coefs(self, coefM=0.0, coefK=0.0):
        self.__coefM = coefM
        self.__coefK = coefK

    def Get_Rayleigh_Damping(self) -> sparse.csr_matrix:
        if self.problemType == "displacement":
            try:
                return self.__coefM * self.__Mu + self.__coefK * self.__Ku
            except:
                # "Mu n'a pas été calculé"
                return None
        else:
            return None    

    def Solve_u(self, steadyState=True) -> np.ndarray:
        """Resolution du probleme de déplacement"""

        if not self.__Check_Autorisation(["displacement","damage"]): return

        if self.__problemType not in ["displacement","damage"]:
            print("La simulation n'est pas une simulation en déplacement")
            return

        if steadyState:
            Uglob = self.__Solveur(problemType="displacement", algo="elliptic")
        else:
            Uglob = self.__Solveur(problemType="displacement", algo="hyperbolic")
        
        assert Uglob.shape[0] == self.mesh.Nn*self.__dim

        self.__displacement = Uglob
       
        return self.__displacement.copy()

# ------------------------------------------- PROBLEME POUTRE ------------------------------------------- 

    def ConstruitMatElem_Beam(self) -> np.ndarray:
        """Construit les matrices de rigidités élementaires pour le problème en déplacement

        Returns:
            Ku_beam: les matrices elementaires pour chaque groupe d'element 
        """

        if not self.__Check_Autorisation(["beam"]): return

        # Data
        mesh = self.__mesh
        if not mesh.groupElem.dim == 1: return
        groupElem = mesh.groupElem

        # Récupération du maodel poutre
        beamModel = self.materiau.beamModel
        if not isinstance(beamModel, BeamModel): return
        
        if beamModel.dim == 1:
            matriceType="rigi"
        else:
            matriceType="beam"
        
        tic = Tic()
        
        jacobien_e_pg = mesh.Get_jacobien_e_pg(matriceType)
        poid_pg = mesh.Get_poid_pg(matriceType)

        D_e_pg = beamModel.Calc_D_e_pg(groupElem, matriceType)
        
        B_beam_e_pg = self.__Get_B_beam_e_pg(matriceType)
        
        Kbeam_e = np.einsum('ep,p,epji,epjk,epkl->eil', jacobien_e_pg, poid_pg, B_beam_e_pg, D_e_pg, B_beam_e_pg, optimize='optimal')
            
        tic.Tac("Matrices","Construction Kbeam_e", self.__verbosity)

        return Kbeam_e

    def __Get_B_beam_e_pg(self, matriceType: str):

        # Exemple matlab : FEMOBJECT/BASIC/MODEL/ELEMENTS/@BEAM/calc_B.m

        tic = Tic()

        # Récupération du maodel poutre
        beamModel = self.materiau.beamModel
        assert isinstance(beamModel, BeamModel)
        dim = beamModel.dim
        nbddl_n = beamModel.nbddl_n

        # Data
        mesh = self.__mesh
        jacobien_e_pg = mesh.Get_jacobien_e_pg(matriceType)
        groupElem = mesh.groupElem
        elemType = groupElem.elemType
        nPe = groupElem.nPe
        Ne = jacobien_e_pg.shape[0]
        nPg = jacobien_e_pg.shape[1]

        # Recupère les matrices pour travailler
        dN_e_pg = mesh.Get_dN_sclaire_e_pg(matriceType)
        if beamModel.dim > 1:
            ddNv_e_pg = mesh.Get_ddNv_sclaire_e_pg(matriceType)

        if dim == 1:
            # u = [u1, . . . , un]
            
            # repu = np.arange(0,3*nPe,3) # [0,3] (SEG2) [0,3,6] (SEG3)
            if elemType == "SEG2":
                repu = [0,1]
            elif elemType == "SEG3":
                repu = [0,1,2]

            B_e_pg = np.zeros((Ne, nPg, 1, nbddl_n*nPe))
            B_e_pg[:,:,0, repu] = dN_e_pg[:,:,0]
                

        elif dim == 2:
            # u = [u1, v1, rz1, . . . , un, vn, rzn]
            
            # repu = np.arange(0,3*nPe,3) # [0,3] (SEG2) [0,3,6] (SEG3)
            if elemType == "SEG2":
                repu = [0,3]
                repv = [1,2,4,5]
            elif elemType == "SEG3":
                # TODO il faut redefinir les fonctions de formes Nv dNv ddNv pour SEG3
                repu = [0,3,6]
                repv = [1,2,4,5,7,8]

            B_e_pg = np.zeros((Ne, nPg, 2, nbddl_n*nPe))
            
            B_e_pg[:,:,0, repu] = dN_e_pg[:,:,0]
            B_e_pg[:,:,1, repv] = ddNv_e_pg[:,:,0]

        elif dim == 3:
            # u = [u1, v1, w1, rx1, ry1, rz1, u2, v2, w2, rx2, ry2, rz2]

            if elemType == "SEG2":
                repux = [0,6]
                repvy = [1,5,7,11]
                repvz = [2,4,8,10]
                reptx = [3,9]
            elif elemType == "SEG3":
                repux = [0,6,12]
                repvy = [1,5,7,11,13,17]
                repvz = [2,4,8,10,14,16]
                reptx = [3,9,15]

            B_e_pg = np.zeros((Ne, nPg, 4, nbddl_n*nPe))
            
            B_e_pg[:,:,0, repux] = dN_e_pg[:,:,0]
            B_e_pg[:,:,1, reptx] = dN_e_pg[:,:,0]
            B_e_pg[:,:,3, repvy] = ddNv_e_pg[:,:,0]
            ddNvz_e_pg = ddNv_e_pg.copy()
            ddNvz_e_pg[:,:,0,[1,3]] *= -1 # RY = -UZ'
            B_e_pg[:,:,2, repvz] = ddNvz_e_pg[:,:,0]

        # Fait la rotation si nécessaire

        if dim == 1:
            B_beam_e_pg = B_e_pg
        else:
            P = mesh.groupElem.sysCoord_e
            Pglob_e = np.zeros((Ne, nbddl_n*nPe, nbddl_n*nPe))
            Ndim = nbddl_n*nPe
            N = P.shape[1]
            listlignes = np.repeat(range(N), N)
            listColonnes = np.array(list(range(N))*N)
            for e in range(nbddl_n*nPe//3):
                Pglob_e[:,listlignes + e*N, listColonnes + e*N] = P[:,listlignes,listColonnes]

            B_beam_e_pg = np.einsum('epij,ejk->epik', B_e_pg, Pglob_e, optimize='optimal')

        tic.Tac("Matrices","Construction B_beam_e_pg", False)

        return B_beam_e_pg

    def Assemblage_beam(self):
        """Construit K global pour le problème en deplacement
        """

        if not self.__Check_Autorisation(["beam"]): return

        # Data
        mesh = self.__mesh        

        model = self.materiau.beamModel

        assert isinstance(model, BeamModel)

        taille = mesh.Nn * model.nbddl_n

        Ku_beam = self.ConstruitMatElem_Beam()

        # Dimension supplémentaire lié a l'utilisation des coefs de lagrange
        dimSupl = len(self.__Bc_Lagrange)
        if dimSupl > 0:
            dimSupl += len(self.Get_ddls_Dirichlet("beam"))

        # Prépare assemblage
        lignesVector_e = mesh.lignesVectorBeam_e(model.nbddl_n)
        colonnesVector_e = mesh.colonnesVectorBeam_e(model.nbddl_n)
        
        tic = Tic()

        # Assemblage
        self.__Kbeam = sparse.csr_matrix((Ku_beam.reshape(-1), (lignesVector_e.reshape(-1), colonnesVector_e.reshape(-1))), shape=(taille+dimSupl, taille+dimSupl))
        """Matrice Kglob pour le problème poutre (Nn*nbddl_e, Nn*nbddl_e)"""

        # Ici j'initialise Fu calr il faudrait calculer les forces volumiques dans __ConstruitMatElem_Dep !!!
        self.__Fbeam = sparse.csr_matrix((taille+dimSupl, 1))
        """Vecteur Fglob pour le problème poutre (Nn*nbddl_e, 1)"""

        # import matplotlib.pyplot as plt
        # plt.figure()
        # plt.spy(self.__Ku)
        # plt.show()

        tic.Tac("Matrices","Assemblage Kbeam et Fbeam", self.__verbosity)
        return self.__Kbeam

    def Solve_beam(self) -> np.ndarray:
        """Resolution du probleme poutre""" 

        if not self.__Check_Autorisation(["beam"]): return

        Uglob_beam = self.__Solveur(problemType="beam", algo="elliptic")
        
        assert Uglob_beam.shape[0] == self.mesh.Nn*self.materiau.beamModel.nbddl_n

        self.__beamDisplacement = Uglob_beam
       
        return self.__beamDisplacement.copy()

# ------------------------------------------- PROBLEME ENDOMMAGEMENT ------------------------------------------- 

    def Calc_psiPlus_e_pg(self):
        """Calcul de la densité denergie positive\n
        Pour chaque point de gauss de tout les elements du maillage on va calculer psi+
       
        Returns:
            np.ndarray: self.__psiP_e_pg
        """

        if not self.__Check_Autorisation(["damage"]): return

        assert self.materiau.isDamaged, "pas de modèle d'endommagement"

        phaseFieldModel = self.materiau.phaseFieldModel
        
        u = self.__displacement
        d = self.__damage

        testu = isinstance(u, np.ndarray) and (u.shape[0] == self.__mesh.Nn*self.__dim )
        testd = isinstance(d, np.ndarray) and (d.shape[0] == self.__mesh.Nn )

        assert testu or testd,"Problème de dimension"

        Epsilon_e_pg = self.__Calc_Epsilon_e_pg(u, "masse")            
        # ici le therme masse est important sinon on sous intègre

        # Calcul l'energie
        psiP_e_pg, psiM_e_pg = phaseFieldModel.Calc_psi_e_pg(Epsilon_e_pg)

        if phaseFieldModel.solveur == "History":
            # Récupère l'ancien champ d'histoire
            old_psiPlus_e_pg = self.__old_psiP_e_pg
            
            if isinstance(old_psiPlus_e_pg, list) and len(old_psiPlus_e_pg) == 0:
                # Pas encore d'endommagement disponible
                old_psiPlus_e_pg = np.zeros_like(psiP_e_pg)

            inc_H = psiP_e_pg - old_psiPlus_e_pg

            elements, pdGs = np.where(inc_H < 0)

            psiP_e_pg[elements, pdGs] = old_psiPlus_e_pg[elements, pdGs]

            # new = np.linalg.norm(psiP_e_pg)
            # old = np.linalg.norm(self.__old_psiP_e_pg)
            # assert new >= old, "Erreur"
            
        self.__psiP_e_pg = psiP_e_pg


        return self.__psiP_e_pg
    
    def __ConstruitMatElem_Pfm(self):
        """Construit les matrices élementaires pour le problème d'endommagement

        Returns:
            Kd_e, Fd_e: les matrices elementaires pour chaque element
        """

        if not self.__Check_Autorisation(["damage"]): return

        phaseFieldModel = self.materiau.phaseFieldModel

        # Data
        k = phaseFieldModel.k
        PsiP_e_pg = self.Calc_psiPlus_e_pg()
        r_e_pg = phaseFieldModel.get_r_e_pg(PsiP_e_pg)
        f_e_pg = phaseFieldModel.get_f_e_pg(PsiP_e_pg)

        matriceType="masse"

        mesh = self.__mesh

        # Probleme de la forme K*Laplacien(d) + r*d = F        
        ReactionPart_e_pg = mesh.Get_phaseField_ReactionPart_e_pg(matriceType) # -> jacobien_e_pg * poid_pg * Nd_pg' * Nd_pg
        DiffusePart_e_pg = mesh.Get_phaseField_DiffusePart_e_pg(matriceType) # -> jacobien_e_pg, poid_pg, Bd_e_pg', Bd_e_pg
        SourcePart_e_pg = mesh.Get_phaseField_SourcePart_e_pg(matriceType) # -> jacobien_e_pg, poid_pg, Nd_pg'
        
        tic = Tic()

        # useNumba = self.__useNumba
        useNumba = False        
        if useNumba:
            # Moin rapide et beug Fd_e

            Kd_e, Fd_e = CalcNumba.Construit_Kd_e_and_Fd_e(r_e_pg, ReactionPart_e_pg,
            k, DiffusePart_e_pg,
            f_e_pg, SourcePart_e_pg)
            # testFd_e = np.einsum('ep,epij->eij', f_e_pg, SourcePart_e_pg, optimize='optimal') - Fd_e

            # assert np.max(testFd_e) == 0, "Erreur"

            # K_r_e = np.einsum('ep,epij->eij', r_e_pg, ReactionPart_e_pg, optimize='optimal')
            # K_K_e = np.einsum('epij->eij', DiffusePart_e_pg * k, optimize='optimal')
            # testFd_e = np.einsum('ep,epij->eij', f_e_pg, SourcePart_e_pg, optimize='optimal') - Fd_e
            # testKd_e = K_r_e+K_K_e - Kd_e

        else:
            # Plus rapide sans beug

            # jacobien_e_pg = mesh.Get_jacobien_e_pg(matriceType)
            # poid_pg = mesh.Get_poid_pg(matriceType)
            # Nd_pg = mesh.Get_N_scalaire_pg(matriceType)
            # Bd_e_pg = mesh.Get_B_sclaire_e_pg(matriceType)

            # Partie qui fait intervenir le therme de reaction r ->  jacobien_e_pg * poid_pg * r_e_pg * Nd_pg' * Nd_pg
            K_r_e = np.einsum('ep,epij->eij', r_e_pg, ReactionPart_e_pg, optimize='optimal')
            # K_r_e = np.einsum('ep,p,ep,pki,pkj->eij', jacobien_e_pg, poid_pg, r_e_pg, Nd_pg, Nd_pg, optimize='optimal')

            # Partie qui fait intervenir le therme de diffusion K -> jacobien_e_pg, poid_pg, k, Bd_e_pg', Bd_e_pg
            K_K_e = np.einsum('epij->eij', DiffusePart_e_pg * k, optimize='optimal')
            # K_K_e = np.einsum('ep,p,,epki,epkj->eij', jacobien_e_pg, poid_pg, k, Bd_e_pg, Bd_e_pg, optimize='optimal')
            
            # Construit Fd_e -> jacobien_e_pg, poid_pg, f_e_pg, Nd_pg'
            Fd_e = np.einsum('ep,epij->eij', f_e_pg, SourcePart_e_pg, optimize='optimal') #Ici on somme sur les points d'integrations
        
            Kd_e = K_r_e + K_K_e

        tic.Tac("Matrices","Construction Kd_e et Fd_e", self.__verbosity)

        return Kd_e, Fd_e

    def Assemblage_d(self):
        """Construit Kglobal pour le probleme d'endommagement
        """

        if not self.__Check_Autorisation(["damage"]): return
       
        # Data
        mesh = self.__mesh
        taille = mesh.Nn
        lignesScalar_e = mesh.lignesScalar_e
        colonnesScalar_e = mesh.colonnesScalar_e
        
        # Calul les matrices elementaires
        Kd_e, Fd_e = self.__ConstruitMatElem_Pfm()

        # Assemblage
        tic = Tic()        

        self.__Kd = sparse.csr_matrix((Kd_e.reshape(-1), (lignesScalar_e.reshape(-1), colonnesScalar_e.reshape(-1))), shape = (taille, taille))
        """Kglob pour le probleme d'endommagement (Nn, Nn)"""
        
        lignes = mesh.connect.reshape(-1)
        self.__Fd = sparse.csr_matrix((Fd_e.reshape(-1), (lignes,np.zeros(len(lignes)))), shape = (taille,1))
        """Fglob pour le probleme d'endommagement (Nn, 1)"""        

        tic.Tac("Matrices","Assemblage Kd et Fd", self.__verbosity)       

        return self.__Kd, self.__Fd
    
    def Solve_d(self) -> np.ndarray:
        """Resolution du problème d'endommagement"""

        if not self.__Check_Autorisation(["damage"]): return
        
        dGlob = self.__Solveur(problemType="damage", algo="elliptic")

        assert dGlob.shape[0] == self.mesh.Nn

        self.__damage = dGlob

        return self.__damage.copy()

# ------------------------------------------- PROBLEME THERMIQUE -------------------------------------------

    def __ConstruitMatElem_Thermal(self, steadyState: bool) -> np.ndarray:

        if not self.__Check_Autorisation(["thermal"]): return

        thermalModel = self.materiau.thermalModel

        # Data
        k = thermalModel.k

        matriceType="rigi"

        mesh = self.__mesh

        jacobien_e_pg = mesh.Get_jacobien_e_pg(matriceType)
        poid_pg = mesh.Get_poid_pg(matriceType)
        N_e_pg = mesh.Get_N_scalaire_pg(matriceType)
        D_e_pg = mesh.Get_dN_sclaire_e_pg(matriceType)

        Kt_e = np.einsum('ep,p,epji,,epjk->eik', jacobien_e_pg, poid_pg, D_e_pg, k, D_e_pg, optimize="optimal")

        if steadyState:
            return Kt_e
        else:
            ro = self.materiau.ro
            c = thermalModel.c

            Mt_e = np.einsum('ep,p,pji,,,pjk->eik', jacobien_e_pg, poid_pg, N_e_pg, ro, c, N_e_pg, optimize="optimal")

            return Kt_e, Mt_e


    def Assemblage_t(self, steadyState=True) -> tuple[sparse.csr_matrix, sparse.csr_matrix]:
        """Construit Kglobal pour le probleme thermique en régime stationnaire ou non
        """

        if not self.__Check_Autorisation(["thermal"]): return
       
        # Data
        mesh = self.__mesh
        taille = mesh.Nn
        lignesScalar_e = mesh.lignesScalar_e
        colonnesScalar_e = mesh.colonnesScalar_e
        
        # Calul les matrices elementaires
        if steadyState:
            Kt_e = self.__ConstruitMatElem_Thermal(steadyState)
        else:
            Kt_e, Mt_e = self.__ConstruitMatElem_Thermal(steadyState)
        

        # Assemblage
        tic = Tic()

        self.__Kt = sparse.csr_matrix((Kt_e.reshape(-1), (lignesScalar_e.reshape(-1), colonnesScalar_e.reshape(-1))), shape = (taille, taille))
        """Kglob pour le probleme thermique (Nn, Nn)"""
        
        self.__Ft = sparse.csr_matrix((taille, 1))
        """Vecteur Fglob pour le problème en thermique (Nn, 1)"""

        if not steadyState:
            self.__Mt = sparse.csr_matrix((Mt_e.reshape(-1), (lignesScalar_e.reshape(-1), colonnesScalar_e.reshape(-1))), shape = (taille, taille))
            """Mglob pour le probleme thermique (Nn, Nn)"""

        tic.Tac("Matrices","Assemblage Kt et Ft", self.__verbosity)       

        return self.__Kt, self.__Ft

    def Solve_t(self, steadyState=True) -> np.ndarray:
        """Resolution du problème thermique

        Parameters
        ----------
        isStatic : bool, optional
            Le problème est stationnaire, by default True

        Returns
        -------
        np.ndarray
            vecteur solution
        """

        if not self.__Check_Autorisation(["thermal"]): return

        if steadyState:
            thermalGlob = self.__Solveur(problemType="thermal", algo="elliptic")
            # TODO que faire pour -> quand plusieurs types -> np.ndarray ou tuple[np.ndarray, np.ndarray] ?
        else:
            thermalGlob, thermalDotGlob = self.__Solveur(problemType="thermal", algo="parabolic", option=1)

            self.__thermalDot = thermalDotGlob

        assert thermalGlob.shape[0] == self.mesh.Nn

        self.__thermal = thermalGlob

        if steadyState:
            return thermalGlob.copy()
        else:
            return thermalGlob.copy(), thermalDotGlob.copy()

# ------------------------------------------------- SOLVEUR -------------------------------------------------

    def __Solveur(self, problemType: str, algo: str, option=1) -> np.ndarray:
        """Resolution du de la simulation et renvoie la solution\n
        Prépare dans un premier temps A et b pour résoudre Ax=b\n
        On va venir appliquer les conditions limites pour résoudre le système"""

        Simu.CheckProblemTypes(problemType)

        resolution = 1

        if problemType == "beam":
            if len(self.__Bc_Lagrange) > 0:
                resolution = 2
        
        if resolution == 1:
            # --       --  --  --   --  --
            # | Aii Aic |  | xi |   | bi |    
            # | Aci Acc |  | xc | = | bc | 
            # --       --  --  --   --  --
            # ui = inv(Aii) * (bi - Aic * xc)

            tic = Tic()

            # Construit le système matricielle
            b = self.__Application_Conditions_Neuman(problemType, algo, option)
            A, x = self.__Application_Conditions_Dirichlet(problemType, b, resolution, algo, option)

            # Récupère les ddls
            ddl_Connues, ddl_Inconnues = self.__Construit_ddl_connues_inconnues(problemType)

            # Décomposition du système matricielle en connues et inconnues 
            # Résolution de : Aii * ui = bi - Aic * xc
            Aii = A[ddl_Inconnues, :].tocsc()[:, ddl_Inconnues].tocsr()
            Aic = A[ddl_Inconnues, :].tocsc()[:, ddl_Connues].tocsr()
            bi = b[ddl_Inconnues,0]
            xc = x[ddl_Connues,0]

            if problemType == "displacement" and algo == "elliptic":
                x0 = self.__displacement[ddl_Inconnues]
            elif problemType == "displacement" and algo == "hyperbolic":
                x0 = self.__displacement[ddl_Inconnues]
            elif problemType == "damage":
                x0 = self.__damage[ddl_Inconnues]
            elif problemType == "thermal":
                x0 = self.__thermal[ddl_Inconnues]
            elif problemType == "beam":
                x0 = self.__beamDisplacement[ddl_Inconnues]
            else:
                raise "probleme inconnue"

            bDirichlet = Aic.dot(xc) # Plus rapide
            # bDirichlet = np.einsum('ij,jk->ik', Aic.toarray(), xc.toarray(), optimize='optimal')
            # bDirichlet = sparse.csr_matrix(bDirichlet)

            tic.Tac("Matrices","Construit Ax=b", self.__verbosity)

            if problemType in ["displacement","thermal"]:
                # la matrice est definie symétrique positive on peut donc utiliser cholesky
                useCholesky = True
                A_isSymetric = False
            else:
                #la matrice n'est pas definie symétrique positive
                useCholesky = False
                A_isSymetric = False
            
            if problemType == "damage":
                # Si l'endommagement est supérieur à 1 la matrice A n'est plus symétrique
                isDamaged = True
                solveur = self.materiau.phaseFieldModel.solveur
                if solveur == "BoundConstrain":
                    damage = self.damage
                else:
                    damage = []
            else:
                isDamaged = False
                damage = []

            xi = Interface_Solveurs.Solve_Axb(problemType=problemType, A=Aii, b=bi-bDirichlet, x0=x0, isDamaged=isDamaged, damage=damage, useCholesky=useCholesky, A_isSymetric=A_isSymetric, verbosity=self.__verbosity)

            # Reconstruction de la solution
            x = x.toarray().reshape(x.shape[0])
            x[ddl_Inconnues] = xi

        elif resolution == 2:
            # Résolution par la méthode des coefs de lagrange

            tic = Tic()

            # Construit le système matricielle pénalisé
            b = self.__Application_Conditions_Neuman(problemType, algo, option)
            A = self.__Application_Conditions_Dirichlet(problemType, b, resolution, algo, option)

            A = A.tolil()
            b = b.tolil()

            ddls_Dirichlet = np.array(self.Get_ddls_Dirichlet(problemType))
            values_Dirichlet = np.array(self.Get_values_Dirichlet(problemType))

            
            nColEnPlusLagrange = len(self.__Bc_Lagrange)
            nColEnPlusDirichlet = len(ddls_Dirichlet)
            nColEnPlus = nColEnPlusLagrange + nColEnPlusDirichlet

            decalage = A.shape[0]-nColEnPlus

            listeLignesDirichlet = np.arange(decalage, decalage+nColEnPlusDirichlet)
            
            A[listeLignesDirichlet, ddls_Dirichlet] = 1
            A[ddls_Dirichlet, listeLignesDirichlet] = 1
            b[listeLignesDirichlet] = values_Dirichlet

            # Pour chaque condition de lagrange on va rajouter un coef dans la matrice
            for i, lagrangeBc in enumerate(self.__Bc_Lagrange, 1):
                if not isinstance(lagrangeBc, LagrangeCondition): continue
                
                ddls = lagrangeBc.ddls
                valeurs = lagrangeBc.valeurs_ddls
                coefs = lagrangeBc.lagrangeCoefs

                A[ddls,-i] = coefs
                A[-i,ddls] = coefs

                b[-i] = valeurs[0]

            tic.Tac("Matrices","Construit Ax=b", self.__verbosity)

            x = Interface_Solveurs.Solve_Axb(problemType=problemType, A=A, b=b, x0=None,isDamaged=False, damage=[], useCholesky=False, A_isSymetric=False, verbosity=self.__verbosity)

            # Récupère la solution sans les efforts de réactions
            ddl_Connues, ddl_Inconnues = self.__Construit_ddl_connues_inconnues(problemType)
            x = x[range(decalage)]
            return x 
            

        elif resolution == 3:
            # Résolution par la méthode des pénalisations
            
            tic = Tic()

            # Construit le système matricielle pénalisé
            b = self.__Application_Conditions_Neuman(problemType, algo, option)
            A, b = self.__Application_Conditions_Dirichlet(problemType, b, resolution, algo, option)

            ddl_Connues, ddl_Inconnues = self.__Construit_ddl_connues_inconnues(problemType)

            tic.Tac("Matrices","Construit Ax=b", self.__verbosity)

            # Résolution du système matricielle pénalisé
            useCholesky=False #la matrice ne sera pas symétrique definie positive
            A_isSymetric=False
            isDamaged = self.materiau.isDamaged
            if isDamaged:
                solveur = self.materiau.phaseFieldModel.solveur
                if solveur == "BoundConstrain":
                    damage = self.damage
                else:
                    damage = []
            else:
                damage = []

            x = Interface_Solveurs.Solve_Axb(problemType=problemType, A=A, b=b, x0=None,isDamaged=isDamaged, damage=damage, useCholesky=useCholesky, A_isSymetric=A_isSymetric, verbosity=self.__verbosity)

        if problemType == "thermal" and algo == "parabolic":
            thermal_np1 = np.array(x)
            thermalDot = self.__thermalDot.copy()

            alpha = self.__alpha
            dt = self.__dt

            thermalDotTild_np1 = self.__thermal + ((1-alpha) * dt * thermalDot)

            thermalDot_np1 = (thermal_np1 - thermalDotTild_np1)/(alpha*dt)

            return thermal_np1, thermalDot_np1

        if problemType == "displacement" and algo == "hyperbolic":
            
            if self.__hyperbolicFormulation == "accel":
                a_np1 = np.array(x)
            else:
                u_np1 = np.array(x)

            u_n = self.displacement
            v_n = self.speed
            a_n = self.accel

            dt = self.__dt
            gamma = self.__gamma
            betha = self.__betha

            uTild_np1 = u_n + (dt * v_n) + dt**2/2 * (1-2*betha) * a_n
            vTild_np1 = v_n + (1-gamma) * dt * a_n

            if self.__hyperbolicFormulation == "accel":
                u_np1 = uTild_np1 + betha * dt**2 * a_np1
                v_np1 = vTild_np1 + gamma * dt * a_np1
            else:
                a_np1 = (u_np1 - uTild_np1)/(betha*dt**2)
                v_np1 = vTild_np1 + (gamma * dt * a_np1)

            self.__displacement = u_np1
            self.__speed = v_np1
            self.__accel = a_np1

            return self.displacement

        else:
            return np.array(x)

    def __Construit_ddl_connues_inconnues(self, problemType: str):
        """Récupère les ddl Connues et Inconnues
        Returns:
            list(int), list(int): ddl_Connues, ddl_Inconnues
        """
        
        Simu.CheckProblemTypes(problemType)

        # Construit les ddls connues
        ddls_Connues = []

        ddls_Connues = self.Get_ddls_Dirichlet(problemType)
        unique_ddl_Connues = np.unique(ddls_Connues.copy())

        # Construit les ddls inconnues

        if problemType in ["damage", "thermal"]:
            taille = self.__mesh.Nn
        elif problemType == "displacement":
            taille = self.__mesh.Nn*self.__dim
        elif problemType == "beam":
            taille = self.__mesh.Nn*self.materiau.beamModel.nbddl_n

        ddls_Inconnues = list(np.arange(taille))
        for ddlConnue in ddls_Connues:
            if ddlConnue in ddls_Inconnues:
                ddls_Inconnues.remove(ddlConnue)
                                
        ddls_Inconnues = np.array(ddls_Inconnues)
        
        verifTaille = unique_ddl_Connues.shape[0] + ddls_Inconnues.shape[0]
        assert verifTaille == taille, f"Problème dans les conditions ddls_Connues + ddls_Inconnues - taille = {verifTaille-taille}"

        return ddls_Connues, ddls_Inconnues

    def __Application_Conditions_Neuman(self, problemType: str, algo:str, option=1):
        """Applique les conditions de Neumann"""

        Simu.CheckProblemTypes(problemType)
        
        ddls = self.Get_ddls_Neumann(problemType)
        valeurs_ddls = self.Get_values_Neumann(problemType)

        taille = self.__mesh.Nn

        if problemType == "displacement":
            taille = self.__mesh.Nn*self.__dim
        elif problemType == "beam":
            taille = self.__mesh.Nn*self.materiau.beamModel.nbddl_n

        # Dimension supplémentaire lié a l'utilisation des coefs de lagrange
        dimSupl = len(self.__Bc_Lagrange)
        if dimSupl > 0:
            dimSupl += len(self.Get_ddls_Dirichlet(problemType))
            
        b = sparse.csr_matrix((valeurs_ddls, (ddls,  np.zeros(len(ddls)))), shape = (taille+dimSupl,1))

        # l,c ,v = sparse.find(b)

        if problemType == "damage" and algo == "elliptic":
            b = b + self.__Fd.copy()
        elif problemType == "displacement" and algo == "elliptic":
            b = b + self.__Fu.copy()
        elif problemType == "beam" and algo == "elliptic":
            b = b + self.__Fbeam.copy()
        elif problemType == "displacement" and algo == "hyperbolic":
            b = b + self.__Fu.copy()

            u_n = self.displacement
            v_n = self.speed

            Cu = self.Get_Rayleigh_Damping()
            
            if len(self.__results) == 0 and (b.max() != 0 or b.min() != 0):

                ddl_Connues, ddl_Inconnues = self.__Construit_ddl_connues_inconnues(problemType)

                bb = b - self.__Ku.dot(sparse.csr_matrix(u_n.reshape(-1, 1)))
                
                bb -= Cu.dot(sparse.csr_matrix(v_n.reshape(-1, 1)))

                bbi = bb[ddl_Inconnues]
                Aii = self.__Mu[ddl_Inconnues, :].tocsc()[:, ddl_Inconnues].tocsr()

                ai_n = Interface_Solveurs.Solve_Axb(problemType=problemType, A=Aii, b=bbi, x0=None, isDamaged=False, damage=[], useCholesky=False, A_isSymetric=True, verbosity=self.__verbosity)

                self.__accel[ddl_Inconnues] = ai_n
            
            a_n = self.accel

            dt = self.__dt
            gamma = self.__gamma
            betha = self.__betha

            uTild_np1 = u_n + (dt * v_n) + dt**2/2 * (1-2*betha) * a_n
            vTild_np1 = v_n + (1-gamma) * dt * a_n

            if self.__hyperbolicFormulation == "accel":
                b -= self.__Ku.dot(sparse.csr_matrix(uTild_np1.reshape(-1,1)))
                b -= Cu.dot(sparse.csr_matrix(vTild_np1.reshape(-1,1)))
            else:
                # Mpart = uTild_np1/(betha * dt**2)
                # b += self.__Mu.copy().dot(sparse.csr_matrix(Mpart.reshape(-1,1)))

                # b -= self.__Cu.dot(sparse.csr_matrix(C1.reshape(-1, 1)))
                
                # Mass_part = self.__Mu + gamma * dt * self.__Cu
                Mass_part = self.__Mu
                b += Mass_part.dot(sparse.csr_matrix(uTild_np1.reshape(-1, 1)))


        elif problemType == "thermal" and algo == "elliptic":
            b = b + self.__Ft.copy()
        elif problemType == "thermal" and algo == "parabolic":
            b = b + self.__Ft.copy()

            thermal = self.__thermal
            thermalDot =  self.__thermalDot

            alpha = self.__alpha
            dt = self.__dt

            thermalDotTild_np1 = thermal + (1-alpha) * dt * thermalDot
            thermalDotTild_np1 = sparse.csr_matrix(thermalDotTild_np1.reshape(-1, 1))

            if option == 1:
                "Resolution de la température"
                b = b + self.__Mt.dot(thermalDotTild_np1/(alpha*dt))
                
            elif option == 2:
                "Résolution de la dérivée temporelle de la température"
                b = b - self.__Kt.dot(thermalDotTild_np1)

            else:
                raise "Configuration inconnue"

        else:
            raise "Configuration inconnue"

        return b

    def __Application_Conditions_Dirichlet(self, problemType: str, b: sparse.csr_matrix, resolution: int, algo: str, option=1):
        """Applique les conditions de dirichlet"""

        Simu.CheckProblemTypes(problemType)

        ddls = self.Get_ddls_Dirichlet(problemType)
        valeurs_ddls = self.Get_values_Dirichlet(problemType)

        taille = self.__mesh.Nn

        if problemType == "damage" and algo == "elliptic":
            A = self.__Kd.copy()
        elif problemType == "displacement" and algo == "elliptic":
            taille = taille*self.__dim
            A = self.__Ku.copy()
        elif problemType == "beam" and algo == "elliptic":
            taille = taille*self.materiau.beamModel.nbddl_n
            A = self.__Kbeam.copy()
        elif problemType == "displacement" and algo == "hyperbolic":
            taille = taille*self.__dim

            # u_n = self.displacement
            # v_n = self.displacementDot

            dt = self.__dt
            gamma = self.__gamma
            betha = self.__betha

            Cu = self.Get_Rayleigh_Damping()

            if self.__hyperbolicFormulation == "accel":
                A = self.__Mu.copy() + (self.__Ku.copy() * betha * dt**2)
                A += (gamma * dt * Cu)

                a_n = self.accel
                valeurs_ddls = a_n[ddls]

            else:

                # uTild_np1 = u_n + (dt * v_n) + dt**2/2 * (1-2*betha) * a_n
                # vTild_np1 = v_n + (1-gamma) * dt * a_n

                # valeurs_ddls =  (u_n - uTild_np1)/(dt**2 * betha)

                A = self.__Mu.copy()/(betha*dt**2) + self.__Ku.copy()
                # A = self.__Mu.copy()/(betha*dt**2) + self.__Ku.copy() + gamma/(dt*betha) * self.__Cu
            
        elif problemType == "thermal" and algo == "elliptic":
            A = self.__Kt.copy()
        elif problemType == "thermal" and algo == "parabolic":
            
            alpha = self.__alpha
            dt = self.__dt

            if option == 1:
                "Resolution de la température"
                A = self.__Kt.copy() + self.__Mt.copy()/(alpha * dt)
                
            elif option == 2:
                "Résolution de la dérivée temporelle de la température"
                A = self.__Kt.copy() * alpha * dt + self.__Mt.copy()

            else:
                raise "Configuration inconnue"

        else:
            raise "Configuration inconnue"


        if resolution == 1:
            
            # ici on renvoie la solution avec les ddls connues
            x = sparse.csr_matrix((valeurs_ddls, (ddls,  np.zeros(len(ddls)))), shape = (taille,1), dtype=np.float64)

            # l,c ,v = sparse.find(x)

            return A, x

        elif resolution == 2:

            return A

        elif resolution == 3:
            # Pénalisation

            A = A.tolil()
            b = b.tolil()            
            
            # Pénalisation A
            A[ddls] = 0.0
            A[ddls, ddls] = 1

            # Pénalisation b
            b[ddls] = valeurs_ddls

            # ici on renvoie A pénalisé
            return A.tocsr(), b.tocsr()
            

    def Set_Parabolic_AlgoProperties(self, alpha=1/2, dt=0.1):
        """Renseigne les propriétes de résolution de l'algorithme

        Parameters
        ----------
        alpha : float, optional
            critère alpha [0 -> Forward Euler, 1 -> Backward Euler, 1/2 -> midpoint], by default 1/2
        dt : float, optional
            incrément temporel, by default 0.1
        """

        # assert alpha >= 0 and alpha <= 1, "alpha doit être compris entre [0, 1]"
        # TODO Est-il possible davoir au dela de 1 ?

        assert dt > 0, "l'incrément temporel doit être > 0"

        self.__alpha = alpha
        self.__dt = dt

    """

        Parameters
        ----------
        alpha : float, optional
            critère alpha [0 -> Forward Euler, 1 -> Backward Euler, 1/2 -> midpoint], by default 1/2
        dt : float, optional
            incrément temporel, by default 0.1
        """
    def Set_Hyperbolic_AlgoProperties(self, betha=1/4, gamma=1/2, dt=0.1):
        """Renseigne les propriétes de résolution de l'algorithme

        Parameters
        ----------
        betha : float, optional
            coef betha, by default 1/4
        gamma : float, optional
            coef gamma, by default 1/2
        dt : float, optional
            incrément temporel, by default 0.1
        """

        # assert alpha >= 0 and alpha <= 1, "alpha doit être compris entre [0, 1]"
        # TODO Est-il possible davoir au dela de 1 ?

        assert dt > 0, "l'incrément temporel doit être > 0"

        self.__betha = betha
        self.__gamma = gamma
        self.__dt = dt
        self.__hyperbolicFormulation = "accel"

# ------------------------------------------- CONDITIONS LIMITES -------------------------------------------

    @staticmethod
    def CheckDirections(dim: int, problemType:str, directions:list):
        """Verifie si les directions renseignées sont possible pour le probleme"""
        Simu.CheckProblemTypes(problemType)
        
        if problemType in ["damage", "thermal"]:
            # Ici on travail sur un champ scalaire, il n'y a pas de direction à renseigné
            pass
        elif problemType == "displacement":
            for d in directions:
                assert d in ["x","y","z"]
                if dim == 2: assert d != "z", "Lors d'une simulation 2d on ne peut appliquer ques des conditions suivant x et y"
            assert dim >= len(directions)
        elif problemType == "beam":
            if dim == 1:
                list = ["x"]
            elif dim == 2:
                list = ["x","y","rz"]
            elif dim == 3:
                list = ["x","y","z","rx","ry","rz"]

            for d in directions:
                assert d in list

    def __Get_indexe_option(self, option):

        problemType = self.__problemType
        dim = self.dim

        if problemType in ["displacement","damage"]:
            # "Stress" : ["Sxx", "Syy", "Sxy"]
            # "Stress" : ["Sxx", "Syy", "Szz", "Syz", "Sxz", "Sxy"]
            # "Accel" : ["vx", "vy", "vz", "ax", "ay", "az"]

            if option in ["x","fx","dx","vx","ax"]:
                return 0
            elif option in ["y","fy","dy","vy","ay"]:
                return 1
            elif option in ["z","fz","dz","vz","az"]:
                return 2
            elif option in ["Sxx","Exx"]:
                return 0
            elif option in ["Syy","Eyy"]:
                return 1
            elif option in ["Sxy","Exy"]:
                if dim == 2:
                    return 2
                elif dim == 3:
                    return 5
            elif option in ["Syy","Eyy"]:
                return 1
            elif option in ["Szz","Ezz"]:
                return 2
            elif option in ["Syz","Eyz"]:
                return 3
            elif option in ["Sxz","Exz"]:
                return 4
        elif problemType == "beam":

            # "Beam1D" : ["u" "fx"]
            # "Beam2D : ["u","v","rz""fx", "fy", "cz"]
            # "Beam3D" : ["u", "v", "w", "rx", "ry", "rz" "fx","fy","fz","cx","cy"]

            if option in ["u","fx"]:
                return 0
            elif option in ["v","fy"]:
                return 1
            elif option in ["w","fz"]:
                return 2
            elif option in ["rx"]:
                return 3
            elif option in ["ry"]:
                return 4
            elif option in ["rz"]:
                if dim == 2: 
                    return 2
                elif dim == 3: 
                    return 5

    def Init_Bc(self):
        """Initie les conditions limites de dirichlet et de Neumann"""
        self.__Init_Bc_Dirichlet()
        self.__Init_Bc_Neumann()
        self.__Init_Bc_Lagrange()

    def __Init_Bc_Neumann(self):
        """Initialise les conditions limites de Neumann"""
        self.__Bc_Neumann = []
        """Conditions de Neumann list(BoundaryCondition)"""

    def __Init_Bc_Lagrange(self):
        """Initialise les conditions limites de Lagrange"""
        self.__Bc_Lagrange = []
        """Conditions de Lagrange list(BoundaryCondition)"""
        self.__Bc_LagrangeAffichage = []
        """Conditions de Lagrange list(BoundaryCondition)"""

    def __Init_Bc_Dirichlet(self):
        """Initialise les conditions limites de Dirichlet"""
        self.__Bc_Dirichlet = []
        """Conditions de Dirichlet list(BoundaryCondition)"""

    def Get_Bc_Dirichlet(self):
        """Renvoie une copie des conditions de Dirichlet"""
        return self.__Bc_Dirichlet.copy()
    
    def Get_Bc_Neuman(self):
        """Renvoie une copie des conditions de Neumann"""
        return self.__Bc_Neumann.copy()

    def Get_Bc_Lagrange(self):
        """Renvoie une copie des conditions de Lagrange"""
        return self.__Bc_Lagrange.copy()
    
    def Get_Bc_LagrangeAffichage(self):
        """Renvoie une copie des conditions de Lagrange pour l'affichage"""
        return self.__Bc_LagrangeAffichage.copy()

    def Get_ddls_Dirichlet(self, problemType: str) -> list:
        """Renvoie les ddls liés aux conditions de Dirichlet"""
        return BoundaryCondition.Get_ddls(problemType, self.__Bc_Dirichlet)

    def Get_values_Dirichlet(self, problemType: str) -> list:
        """Renvoie les valeurs ddls liés aux conditions de Dirichlet"""
        return BoundaryCondition.Get_values(problemType, self.__Bc_Dirichlet)
    
    def Get_ddls_Neumann(self, problemType: str) -> list:
        """Renvoie les ddls liés aux conditions de Neumann"""
        return BoundaryCondition.Get_ddls(problemType, self.__Bc_Neumann)
    
    def Get_values_Neumann(self, problemType: str) -> list:
        """Renvoie les valeurs ddls liés aux conditions de Neumann"""
        return BoundaryCondition.Get_values(problemType, self.__Bc_Neumann)

    def Get_ddls_Lagrange(self, problemType: str) -> list:
        """Renvoie les ddls liés aux conditions de Lagrange"""
        return BoundaryCondition.Get_ddls(problemType, self.__Bc_Lagrange)
    
    def Get_values_Lagrange(self, problemType: str) -> list:
        """Renvoie les valeurs ddls liés aux conditions de Lagrange"""
        return BoundaryCondition.Get_values(problemType, self.__Bc_Lagrange)

    def __evalue(self, coordo: np.ndarray, valeurs, option="noeuds"):
        """evalue les valeurs aux noeuds ou aux points de gauss"""
        
        assert option in ["noeuds","gauss"]        
        if option == "noeuds":
            valeurs_eval = np.zeros(coordo.shape[0])
        elif option == "gauss":
            valeurs_eval = np.zeros((coordo.shape[0],coordo.shape[1]))
        
        if isinstance(valeurs, LambdaType):
            # Evalue la fonction aux coordonnées
            try:
                if option == "noeuds":
                    valeurs_eval[:] = valeurs(coordo[:,0], coordo[:,1], coordo[:,2])
                elif option == "gauss":
                    valeurs_eval[:,:] = valeurs(coordo[:,:,0], coordo[:,:,1], coordo[:,:,2])
            except:
                raise "Doit fournir une fonction lambda de la forme\n lambda x,y,z, : f(x,y,z)"
        else:            
            if option == "noeuds":
                valeurs_eval[:] = valeurs
            elif option == "gauss":
                valeurs_eval[:,:] = valeurs

        return valeurs_eval
    
    def add_dirichlet(self, problemType: str, noeuds: np.ndarray, valeurs: np.ndarray, directions: list, description=""):
        
        Nn = noeuds.shape[0]
        coordo = self.mesh.coordo
        coordo_n = coordo[noeuds]

        # initialise le vecteur de valeurs pour chaque noeuds
        valeurs_ddl_dir = np.zeros((Nn, len(directions)))

        for d, dir in enumerate(directions):
            eval_n = self.__evalue(coordo_n, valeurs[d], option="noeuds")
            valeurs_ddl_dir[:,d] = eval_n.reshape(-1)
        
        valeurs_ddls = valeurs_ddl_dir.reshape(-1)

        if problemType == "beam":
            param = self.materiau.beamModel.nbddl_n
        else:
            param = self.__dim

        ddls = BoundaryCondition.Get_ddls_noeuds(param, problemType, noeuds, directions)

        self.__Add_Bc_Dirichlet(problemType, noeuds, valeurs_ddls, ddls, directions, description)

    def add_pointLoad(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list, description=""):
        """Pour le probleme donné applique une force ponctuelle\n
        valeurs est une liste de constantes ou de fonctions\n
        ex: valeurs = [lambda x,y,z : f(x,y,z) ou -10]

        les fonctions doivent être de la forme lambda x,y,z : f(x,y,z)\n
        les fonctions utilisent les coordonnées x, y et z des noeuds renseignés
        """

        valeurs_ddls, ddls = self.__pointLoad(problemType, noeuds, valeurs, directions)

        self.__Add_Bc_Neumann(problemType, noeuds, valeurs_ddls, ddls, directions, description)
        
    def add_lineLoad(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list, description=""):
        """Pour le probleme donné applique une force linéique\n
        valeurs est une liste de constantes ou de fonctions\n
        ex: valeurs = [lambda x,y,z : f(x,y,z) ou -10]

        les fonctions doivent être de la forme lambda x,y,z : f(x,y,z)\n
        les fonctions utilisent les coordonnées x, y et z des points d'intégrations
        """

        valeurs_ddls, ddls = self.__lineLoad(problemType, noeuds, valeurs, directions)

        self.__Add_Bc_Neumann(problemType, noeuds, valeurs_ddls, ddls, directions, description)

    def add_surfLoad(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list, description=""):
        """Pour le probleme donné applique une force surfacique\n
        valeurs est une liste de constantes ou de fonctions\n
        ex: valeurs = [lambda x,y,z : f(x,y,z) ou -10]

        les fonctions doivent être de la forme lambda x,y,z : f(x,y,z)\n
        les fonctions utilisent les coordonnées x, y et z des points d'intégrations\n
        Si probleme poutre on integre sur la section de la poutre
        """

        if problemType == "beam":
            valeurs_ddls, ddls = self.__pointLoad(problemType, noeuds, valeurs, directions)
            # multiplie par la surface de la section
            # TODO ici il peut y avoir un probleme si il ya plusieurs poutres et donc des sections différentes
            valeurs_ddls *= self.materiau.beamModel.poutre.section.aire
        elif self.__dim == 2:
            valeurs_ddls, ddls = self.__lineLoad(problemType, noeuds, valeurs, directions)
            # multiplie par l'epaisseur
            valeurs_ddls *= self.materiau.epaisseur
        elif self.__dim == 3:
            valeurs_ddls, ddls = self.__surfload(problemType, noeuds, valeurs, directions)

        self.__Add_Bc_Neumann(problemType, noeuds, valeurs_ddls, ddls, directions, description)

    def add_volumeLoad(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list, description=""):
        """Pour le probleme donné applique une force volumique\n
        valeurs est une liste de constantes ou de fonctions\n
        ex: valeurs = [lambda x,y,z : f(x,y,z) ou -10]

        les fonctions doivent être de la forme lambda x,y,z : f(x,y,z)\n
        les fonctions utilisent les coordonnées x, y et z des points d'intégrations
        """
        if problemType == "beam":
            valeurs_ddls, ddls = self.__lineLoad(problemType, noeuds, valeurs, directions)
            # multiplie par la surface de la section
            # TODO ici il peut y avoir un probleme si il ya plusieurs poutres et donc des sections différentes
            valeurs_ddls *= self.materiau.beamModel.poutre.section.aire
        elif self.__dim == 2:
            valeurs_ddls, ddls = self.__surfload(problemType, noeuds, valeurs, directions)
            # multiplie par l'epaisseur
            valeurs_ddls = valeurs_ddls*self.materiau.epaisseur
        elif self.__dim == 3:
            valeurs_ddls, ddls = self.__volumeload(problemType, noeuds, valeurs, directions)

        self.__Add_Bc_Neumann(problemType, noeuds, valeurs_ddls, ddls, directions, description)

    def __pointLoad(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list):
        """Applique une force linéique\n
        Renvoie valeurs_ddls, ddls"""

        Nn = noeuds.shape[0]
        coordo = self.mesh.coordo
        coordo_n = coordo[noeuds]

        # initialise le vecteur de valeurs pour chaque noeuds
        valeurs_ddl_dir = np.zeros((Nn, len(directions)))

        for d, dir in enumerate(directions):
            eval_n = self.__evalue(coordo_n, valeurs[d]/len(noeuds), option="noeuds")
            valeurs_ddl_dir[:,d] = eval_n.reshape(-1)
        
        valeurs_ddls = valeurs_ddl_dir.reshape(-1)

        if problemType == "beam":
            param = self.materiau.beamModel.nbddl_n
        else:
            param = self.__dim

        ddls = BoundaryCondition.Get_ddls_noeuds(param, problemType, noeuds, directions)

        return valeurs_ddls, ddls

    def __IntegrationDim(self, dim: int, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list):

        valeurs_ddls=np.array([])
        ddls=np.array([], dtype=int)

        listGroupElemDim = self.mesh.Get_list_groupElem(dim)

        if len(listGroupElemDim) > 1:
            exclusivement=True
        else:
            exclusivement=True

        if problemType == "beam":
            param = self.materiau.beamModel.nbddl_n
        else:
            param = self.__dim

        # Récupération des matrices pour le calcul
        for groupElem in listGroupElemDim:

            # Récupère les elements qui utilisent exclusivement les noeuds
            elements = groupElem.get_elementsIndex(noeuds, exclusivement=exclusivement)
            if elements.shape[0] == 0: continue
            connect_e = groupElem.connect_e[elements]
            Ne = elements.shape[0]
            
            # récupère les coordonnées des points de gauss dans le cas ou on a besoin dévaluer la fonction
            coordo_e_p = groupElem.get_coordo_e_p("masse",elements)
            nPg = coordo_e_p.shape[1]

            N_pg = groupElem.get_N_pg("masse")

            # objets d'integration
            jacobien_e_pg = groupElem.get_jacobien_e_pg("masse")[elements]
            gauss = groupElem.get_gauss("masse")
            poid_pg = gauss.poids

            # initialise le vecteur de valeurs pour chaque element et chaque pts de gauss
            valeurs_ddl_dir = np.zeros((Ne*groupElem.nPe, len(directions)))

            # Intègre sur chaque direction
            for d, dir in enumerate(directions):
                eval_e_p = self.__evalue(coordo_e_p, valeurs[d], option="gauss")
                valeurs_e_p = np.einsum('ep,p,ep,pij->epij', jacobien_e_pg, poid_pg, eval_e_p, N_pg, optimize='optimal')
                valeurs_e = np.sum(valeurs_e_p, axis=1)
                valeurs_ddl_dir[:,d] = valeurs_e.reshape(-1)

            new_valeurs_ddls = valeurs_ddl_dir.reshape(-1)
            valeurs_ddls = np.append(valeurs_ddls, new_valeurs_ddls)
            
            new_ddls = BoundaryCondition.Get_ddls_connect(param, problemType, connect_e, directions)
            ddls = np.append(ddls, new_ddls)

        return valeurs_ddls, ddls

    def __lineLoad(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list):
        """Applique une force linéique\n
        Renvoie valeurs_ddls, ddls"""

        Simu.CheckProblemTypes(problemType)
        Simu.CheckDirections(self.__dim, problemType, directions)

        valeurs_ddls, ddls = self.__IntegrationDim(dim=1, problemType=problemType, noeuds=noeuds, valeurs=valeurs, directions=directions)

        return valeurs_ddls, ddls
    
    def __surfload(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list):
        """Applique une force surfacique\n
        Renvoie valeurs_ddls, ddls"""

        Simu.CheckProblemTypes(problemType)
        Simu.CheckDirections(self.__dim, problemType, directions)

        valeurs_ddls, ddls = self.__IntegrationDim(dim=2, problemType=problemType, noeuds=noeuds, valeurs=valeurs, directions=directions)

        return valeurs_ddls, ddls

    def __volumeload(self, problemType:str, noeuds: np.ndarray, valeurs: list, directions: list):
        """Applique une force surfacique\n
        Renvoie valeurs_ddls, ddls"""

        Simu.CheckProblemTypes(problemType)
        Simu.CheckDirections(self.__dim, problemType, directions)

        valeurs_ddls, ddls = self.__IntegrationDim(dim=3, problemType=problemType, noeuds=noeuds, valeurs=valeurs, directions=directions)

        return valeurs_ddls, ddls
    
    def __Add_Bc_Neumann(self, problemType: str, noeuds: np.ndarray, valeurs_ddls: np.ndarray, ddls: np.ndarray, directions: list, description=""):
        """Ajoute les conditions de Neumann"""

        tic = Tic()
        
        Simu.CheckProblemTypes(problemType)
        Simu.CheckDirections(self.__dim, problemType, directions)

        if problemType in ["damage","thermal"]:
            
            new_Bc = BoundaryCondition(problemType, noeuds, ddls, directions, valeurs_ddls, f'Neumann {description}')

        elif problemType in ["displacement","beam"]:

            # Si un ddl est déja connue dans les conditions de dirichlet
            # alors on enlève la valeur et le ddl associé
            
            ddl_Dirchlet = self.Get_ddls_Dirichlet(problemType)
            valeursTri_ddls = list(valeurs_ddls)
            ddlsTri = list(ddls.copy())

            def tri(d, ddl):
                if ddl in ddl_Dirchlet:
                    ddlsTri.remove(ddl)
                    valeursTri_ddls.remove(valeurs_ddls[d])

            [tri(d, ddl) for d, ddl in enumerate(ddls)]
            # for d, ddl in enumerate(ddls): 
                

            valeursTri_ddls = np.array(valeursTri_ddls)
            ddlsTri = np.array(ddlsTri)

            new_Bc = BoundaryCondition(problemType, noeuds, ddlsTri, directions, valeursTri_ddls, f'Neumann {description}')

        self.__Bc_Neumann.append(new_Bc)

        tic.Tac("Boundary Conditions","Condition Neumann", self.__verbosity)   
     
    def __Add_Bc_Dirichlet(self, problemType: str, noeuds: np.ndarray, valeurs_ddls: np.ndarray, ddls: np.ndarray, directions: list, description=""):
        """Ajoute les conditions de Dirichlet"""

        tic = Tic()

        Simu.CheckProblemTypes(problemType)

        if problemType in ["damage","thermal"]:
            
            new_Bc = BoundaryCondition(problemType, noeuds, ddls, directions, valeurs_ddls, f'Dirichlet {description}')

        elif problemType in ["displacement","beam"]:

            new_Bc = BoundaryCondition(problemType, noeuds, ddls, directions, valeurs_ddls, f'Dirichlet {description}')

            # Verifie si les ddls de Neumann ne coincidenet pas avec dirichlet
            ddl_Neumann = self.Get_ddls_Neumann(problemType)
            for d in ddls: 
                assert d not in ddl_Neumann, "On ne peut pas appliquer conditions dirchlet et neumann aux memes ddls"

        self.__Bc_Dirichlet.append(new_Bc)

        tic.Tac("Boundary Conditions","Condition Dirichlet", self.__verbosity)

    # ------------------------------------------- LIAISONS ------------------------------------------- 

    # Fonctions pour créer des liaisons entre degré de liberté

    def add_liaison_Encastrement(self, noeuds: np.ndarray, description="Encastrement"):
        
        beamModel = self.materiau.beamModel
        if not isinstance(beamModel, BeamModel):
            print("La simulation n'est pas un probleme poutre")
            return

        if beamModel.dim == 1:
            directions = ['x']
        elif beamModel.dim == 2:
            directions = ['x','y','rz']
        elif beamModel.dim == 3:
            directions = ['x','y','z','rx','ry','rz']

        description = f"Liaison {description}"
        
        self.add_liaisonPoutre(noeuds, directions, description)

    def add_liaison_Rotule(self, noeuds: np.ndarray, directions=[''] ,description="Rotule"):
        
        beamModel = self.materiau.beamModel
        if not isinstance(beamModel, BeamModel):
            print("La simulation n'est pas un probleme poutre")
            return

        if beamModel.dim == 1:
            return
        elif beamModel.dim == 2:
            directions = ['x','y']
        elif beamModel.dim == 3:
            directionsDeBase = ['x','y','z']
            if directions != ['']:
                # On va bloquer les ddls de rotations que ne sont pas dans directions
                directionsRot = ['rx','ry','rz']
                for dir in directions:
                    if dir in directionsRot.copy():
                        directionsRot.remove(dir)

            directions = directionsDeBase
            directions.extend(directionsRot)

        description = f"Liaison {description}"
        
        self.add_liaisonPoutre(noeuds, directions, description)

    def add_liaisonPoutre(self, noeuds: np.ndarray, directions: List[str], description: str):

        beamModel = self.materiau.beamModel
        if not isinstance(beamModel, BeamModel):
            print("La simulation n'est pas un probleme poutre")
            return

        problemType = self.__problemType
        beamModel = self.materiau.beamModel
        nbddl = beamModel.nbddl_n

        # Verficiation
        Simu.CheckDirections(self.__dim, problemType, directions)

        tic = Tic()

        # On va venir pour chaque directions appliquer les conditions
        for d, dir in enumerate(directions):
            ddls = BoundaryCondition.Get_ddls_noeuds(param=nbddl,  problemType=problemType, noeuds=noeuds, directions=[dir])

            new_LagrangeBc = LagrangeCondition(problemType, noeuds, ddls, [dir], [0], [1,-1], description)

            self.__Bc_Lagrange.append(new_LagrangeBc)
        
        # Il n'est pas possible de poser u1-u2 + v1-v2 = 0
        # Il faut appliquer une seule condition à la fois

        tic.Tac("Boundary Conditions","Liaison", self.__verbosity)

        self.__Add_Bc_LagrangeAffichage(noeuds, directions, description)

    def __Add_Bc_LagrangeAffichage(self,noeuds: np.ndarray, directions: List[str], description: str):
        # Ajoute une condition pour l'affichage
        beamModel = self.materiau.beamModel
        nbddl = beamModel.nbddl_n
        
        # Prend le premier noeuds de la liaison
        noeuds1 = np.array([noeuds[0]])

        ddls = BoundaryCondition.Get_ddls_noeuds(param=nbddl,  problemType="beam", noeuds=noeuds1, directions=directions)
        valeurs_ddls =  np.array([0]*len(ddls))

        new_Bc = BoundaryCondition("beam", noeuds1, ddls, directions, valeurs_ddls, description)
        self.__Bc_LagrangeAffichage.append(new_Bc)

    
# ------------------------------------------- POST TRAITEMENT ------------------------------------------- 
    
    def __Calc_Psi_Elas(self):
        """Calcul de l'energie de deformation cinématiquement admissible endommagé ou non
        Calcul de Wdef = 1/2 int_Omega jacobien * poid * Sig : Eps dOmega x epaisseur"""

        sol_u  = self.__displacement

        matriceType = "rigi"
        Epsilon_e_pg = self.__Calc_Epsilon_e_pg(sol_u, matriceType)
        jacobien_e_pg = self.__mesh.Get_jacobien_e_pg(matriceType)
        poid_pg = self.__mesh.Get_poid_pg(matriceType)

        if self.__dim == 2:
            ep = self.materiau.epaisseur
        else:
            ep = 1

        if self.materiau.isDamaged:

            d = self.__damage

            phaseFieldModel = self.materiau.phaseFieldModel
            psiP_e_pg, psiM_e_pg = phaseFieldModel.Calc_psi_e_pg(Epsilon_e_pg)

            # Endommage : psiP_e_pg = g(d) * PsiP_e_pg 
            g_e_pg = phaseFieldModel.get_g_e_pg(d, self.__mesh, matriceType)
            psiP_e_pg = np.einsum('ep,ep->ep', g_e_pg, psiP_e_pg, optimize='optimal')
            psi_e_pg = psiP_e_pg + psiM_e_pg

            Wdef = np.einsum(',ep,p,ep->', ep, jacobien_e_pg, poid_pg, psi_e_pg, optimize='optimal')

        else:

            Sigma_e_pg = self.__Calc_Sigma_e_pg(Epsilon_e_pg, matriceType)
            
            Wdef = 1/2 * np.einsum(',ep,p,epi,epi->', ep, jacobien_e_pg, poid_pg, Sigma_e_pg, Epsilon_e_pg, optimize='optimal')

            # # Calcul par Element fini
            # u_e = self.__mesh.Localises_sol_e(sol_u)
            # Ku_e = self.__ConstruitMatElem_Dep()
            # Wdef = 1/2 * np.einsum('ei,eij,ej->', u_e, Ku_e, u_e, optimize='optimal')
        
        return Wdef

    def __Calc_Psi_Crack(self):
        """Calcul l'energie de fissure"""
        if not self.materiau.isDamaged: return

        pfm = self.materiau.phaseFieldModel 

        Gc = pfm.Gc
        l0 = pfm.l0
        c0 = pfm.c0


        d_n = self.__damage



        d_e = self.__mesh.Localises_sol_e(d_n)
        Kd_e, Fd_e = self.__ConstruitMatElem_Pfm()
        Psi_Crack = 1/2 * np.einsum('ei,eij,ej->', d_e, Kd_e, d_e, optimize='optimal')

        return Psi_Crack

    def __Calc_Epsilon_e_pg(self, sol: np.ndarray, matriceType="rigi"):
        """Construit epsilon pour chaque element et chaque points de gauss

        Parameters
        ----------
        u : np.ndarray
            Vecteur des déplacements

        Returns
        -------
        np.ndarray
            Deformations stockées aux elements et points de gauss (Ne,pg,(3 ou 6))
        """

        useNumba = self.__useNumba
        useNumba = False
        
        tic = Tic()

        if self.__problemType in ["displacement","damage"]:
            # Localise les deplacement par element
            u_e = self.__mesh.Localises_sol_e(sol)
            B_dep_e_pg = self.__mesh.Get_B_dep_e_pg(matriceType)
            if useNumba: # Moins rapide
                Epsilon_e_pg = CalcNumba.epij_ej_to_epi(B_dep_e_pg, u_e)
            else: # Plus rapide
                Epsilon_e_pg = np.einsum('epij,ej->epi', B_dep_e_pg, u_e, optimize='optimal')
        elif self.__problemType == "beam":
            nbddl_n = self.materiau.beamModel.nbddl_n
            assemblyBeam_e = self.mesh.groupElem.assemblyBeam_e(nbddl_n)
            sol_e = sol[assemblyBeam_e]
            B_beam_e_pg = self.__Get_B_beam_e_pg(matriceType)
            Epsilon_e_pg = np.einsum('epij,ej->epi', B_beam_e_pg, sol_e, optimize='optimal')
        
        tic.Tac("Matrices", "Epsilon_e_pg", False)

        return Epsilon_e_pg

    def __Calc_Sigma_e_pg(self, Epsilon_e_pg: np.ndarray, matriceType="rigi") -> np.ndarray:
        """Calcul les contraintes depuis les deformations

        Parameters
        ----------
        Epsilon_e_pg : np.ndarray
            Deformations stockées aux elements et points de gauss (Ne,pg,(3 ou 6))

        Returns
        -------
        np.ndarray
            Renvoie les contrainres endommagé ou non (Ne,pg,(3 ou 6))
        """

        assert Epsilon_e_pg.shape[0] == self.__mesh.Ne
        assert Epsilon_e_pg.shape[1] == self.__mesh.Get_nPg(matriceType)

        useNumba = self.__useNumba

        if self.materiau.isDamaged:

            d = self.__damage

            phaseFieldModel = self.materiau.phaseFieldModel

            SigmaP_e_pg, SigmaM_e_pg = phaseFieldModel.Calc_Sigma_e_pg(Epsilon_e_pg)
            
            # Endommage : Sig = g(d) * SigP + SigM
            g_e_pg = phaseFieldModel.get_g_e_pg(d, self.mesh, matriceType)

            useNumba = False
            tic = Tic()
            if useNumba:
                # Moins rapide 
                SigmaP_e_pg = CalcNumba.ep_epi_to_epi(g_e_pg, SigmaP_e_pg)
            else:
                # Plus rapide
                SigmaP_e_pg = np.einsum('ep,epi->epi', g_e_pg, SigmaP_e_pg, optimize='optimal')

            Sigma_e_pg = SigmaP_e_pg + SigmaM_e_pg
            
        else:

            tic = Tic()

            if self.__problemType == "displacement":

                c = self.materiau.comportement.get_C()
                if useNumba:
                    # Plus rapide sur les gros système > 500 000 ddl (ordre de grandeur)
                    # sinon legerement plus lent
                    Sigma_e_pg = CalcNumba.ij_epj_to_epi(c, Epsilon_e_pg)
                else:
                    # Plus rapide sur les plus petits système
                    Sigma_e_pg = np.einsum('ik,epk->epi', c, Epsilon_e_pg, optimize='optimal')
            
            elif self.__problemType == "beam":

                D_e_pg = self.materiau.beamModel.Calc_D_e_pg(self.mesh.groupElem, matriceType)

                Sigma_e_pg = np.einsum('epij,epj->epi', D_e_pg, Epsilon_e_pg, optimize='optimal')
            
        tic.Tac("Matrices", "Sigma_e_pg", False)

        return Sigma_e_pg


    @staticmethod
    def ResultatsCalculables(dim: int) -> dict:
        if dim == 1:
            options = {
                "Beam" : ["u", "beamDisplacement", "coordoDef", "fx"]
            }
        elif dim == 2:
            options = {
                "Stress" : ["Sxx", "Syy", "Sxy", "Svm","Stress"],
                "Strain" : ["Exx", "Eyy", "Exy", "Evm","Strain"],
                "Displacement" : ["dx", "dy", "dz", "amplitude", "displacement", "coordoDef"],
                "Accel" : ["vx", "vy", "vz", "ax", "ay", "az", "speed", "accel"],
                "Beam" : ["u","v","rz", "amplitude", "beamDisplacement", "coordoDef", "fx", "fy", "cz","Exx","Exy","Sxx","Sxy","Srain","Stress"],
                "Energie" :["Wdef","Psi_Crack","Psi_Elas"],
                "Damage" :["damage","psiP"],
                "Thermal" : ["thermal", "thermalDot"]
            }
        elif dim == 3:
            options = {
                "Stress" : ["Sxx", "Syy", "Szz", "Syz", "Sxz", "Sxy", "Svm","Stress"],
                "Strain" : ["Exx", "Eyy", "Ezz", "Eyz", "Exz", "Exy", "Evm","Strain"],
                "Displacement" : ["dx", "dy", "dz","amplitude","displacement", "coordoDef"],
                "Accel" : ["vx", "vy", "vz", "ax", "ay", "az", "speed", "accel"],
                "Beam" : ["u", "v", "w", "rx", "ry", "rz", "amplitude", "beamDisplacement", "coordoDef", "fx","fy","fz","cx","cy","cz"],
                "Energie" :["Wdef","Psi_Elas"],
                "Thermal" : ["thermal", "thermalDot"]
            }
        return options

    @property
    def __listOptionsDisponible(self) -> List[str]:

        listCategorie = Simu.ResultatsCalculables(self.__dim)

        # Construction de la liste de catégorie en fonction du type de probleme
        problemType = self.__problemType
        # listCategorie = ["Stress", "Strain", "Displacement", "Accel", "Beam", "Energie", "Damage", "Thermal"]
        if problemType == "displacement":
            listCategorieProblem = ["Stress", "Strain", "Displacement", "Accel","Energie"]
        elif problemType == "damage":
            listCategorieProblem = ["Stress", "Strain", "Displacement", "Energie", "Damage"]
        elif problemType == "beam":
            listCategorieProblem = ["Beam"]
        elif problemType == "thermal":
            listCategorieProblem = ["Thermal"]

        listOption = []    

        [listOption.extend(listCategorie[categorie]) for categorie in listCategorieProblem]

        return listOption

    def VerificationOption(self, option):
        """Verification que l'option est bien calculable dans GetResultat

        Parameters
        ----------
        option : str
            option

        Returns
        -------
        Bool
            Réponse du test
        """
        # Construit la liste d'otions pour les résultats en 2D ou 3D
        
        listOptions = self.__listOptionsDisponible
        if option not in listOptions:
            print(f"\nPour un probleme ({self.__problemType}) l'option doit etre dans : \n {listOptions}")
            return False
        else:
            return True

    def Get_Resultat(self, option: str, valeursAuxNoeuds=False, iter=None):
        """ Renvoie le résultat de la simulation
        """

        # TODO A optimiser

        problemType = self.__problemType
        dim = self.__dim
        Ne = self.__mesh.Ne
        Nn = self.__mesh.Nn
        
        if not self.VerificationOption(option): return None

        if iter != None:
            self.Update_iter(iter)

        if problemType == "thermal":

            if option == "thermal":
                return self.__thermal

            if option == "thermalDot":
                try:
                    return self.__thermalDot
                except:
                    print("La simulation thermique est realisé en état d'équilibre")

        elif problemType in ["displacement","damage"]:

            if option in ["Wdef","Psi_Elas"]:
                return self.__Calc_Psi_Elas()
            
            if option == "Psi_Crack":
                return self.__Calc_Psi_Crack()

            if option == "damage":
                return self.damage

            if option == "psiP":
                resultat_e_pg = self.Calc_psiPlus_e_pg()
                resultat = np.mean(resultat_e_pg, axis=1)    

            if option == "displacement":
                return self.displacement

            if option == 'coordoDef':
                return self.GetCoordUglob()

            displacement = self.displacement

            # Deformation et contraintes pour chaque element et chaque points de gauss        
            Epsilon_e_pg = self.__Calc_Epsilon_e_pg(displacement)
            Sigma_e_pg = self.__Calc_Sigma_e_pg(Epsilon_e_pg)

            # Moyenne sur l'élement
            Epsilon_e = np.mean(Epsilon_e_pg, axis=1)
            Sigma_e = np.mean(Sigma_e_pg, axis=1)

            coef = self.materiau.comportement.coef

            # TODO fusionner avec Stress ?

            if "S" in option and not option == "Strain":

                if dim == 2:

                    Sxx_e = Sigma_e[:,0]
                    Syy_e = Sigma_e[:,1]
                    Sxy_e = Sigma_e[:,2]/coef
                    
                    # TODO Ici il faudrait calculer Szz si deformation plane
                    
                    Svm_e = np.sqrt(Sxx_e**2+Syy_e**2-Sxx_e*Syy_e+3*Sxy_e**2)

                    if option == "Sxx":
                        resultat_e = Sxx_e
                    elif option == "Syy":
                        resultat_e = Syy_e
                    elif option == "Sxy":
                        resultat_e = Sxy_e
                    elif option == "Svm":
                        resultat_e = Svm_e

                elif dim == 3:

                    Sxx_e = Sigma_e[:,0]
                    Syy_e = Sigma_e[:,1]
                    Szz_e = Sigma_e[:,2]
                    Syz_e = Sigma_e[:,3]/coef
                    Sxz_e = Sigma_e[:,4]/coef
                    Sxy_e = Sigma_e[:,5]/coef               

                    Svm_e = np.sqrt(((Sxx_e-Syy_e)**2+(Syy_e-Szz_e)**2+(Szz_e-Sxx_e)**2+6*(Sxy_e**2+Syz_e**2+Sxz_e**2))/2)

                    if option == "Sxx":
                        resultat_e = Sxx_e
                    elif option == "Syy":
                        resultat_e = Syy_e
                    elif option == "Szz":
                        resultat_e = Szz_e
                    elif option == "Syz":
                        resultat_e = Syz_e
                    elif option == "Sxz":
                        resultat_e = Sxz_e
                    elif option == "Sxy":
                        resultat_e = Sxy_e
                    elif option == "Svm":
                        resultat_e = Svm_e

                if option == "Stress":
                    resultat_e = np.append(Sigma_e, Svm_e.reshape((Ne,1)), axis=1)

                if valeursAuxNoeuds:
                    resultat_n = self.__InterpolationAuxNoeuds(resultat_e)
                    return resultat_n
                else:
                    return resultat_e
                
            elif "E" in option or option == "Strain":

                if dim == 2:

                    Exx_e = Epsilon_e[:,0]
                    Eyy_e = Epsilon_e[:,1]
                    Exy_e = Epsilon_e[:,2]/coef

                    # TODO Ici il faudrait calculer Ezz si contrainte plane
                    
                    Evm_e = np.sqrt(Exx_e**2+Eyy_e**2-Exx_e*Eyy_e+3*Exy_e**2)

                    if option == "Exx":
                        resultat_e = Exx_e
                    elif option == "Eyy":
                        resultat_e = Eyy_e
                    elif option == "Exy":
                        resultat_e = Exy_e
                    elif option == "Evm":
                        resultat_e = Evm_e

                elif dim == 3:

                    Exx_e = Epsilon_e[:,0]
                    Eyy_e = Epsilon_e[:,1]
                    Ezz_e = Epsilon_e[:,2]
                    Eyz_e = Epsilon_e[:,3]/coef
                    Exz_e = Epsilon_e[:,4]/coef
                    Exy_e = Epsilon_e[:,5]/coef

                    Evm_e = np.sqrt(((Exx_e-Eyy_e)**2+(Eyy_e-Ezz_e)**2+(Ezz_e-Exx_e)**2+6*(Exy_e**2+Eyz_e**2+Exz_e**2))/2)

                    if option == "Exx":
                        resultat_e = Exx_e
                    elif option == "Eyy":
                        resultat_e = Eyy_e
                    elif option == "Ezz":
                        resultat_e = Ezz_e
                    elif option == "Eyz":
                        resultat_e = Eyz_e
                    elif option == "Exz":
                        resultat_e = Exz_e
                    elif option == "Exy":
                        resultat_e = Exy_e
                    elif option == "Evm":
                        resultat_e = Evm_e                
                
                if option == "Strain":
                    resultat_e = np.append(Epsilon_e, Evm_e.reshape((Ne,1)), axis=1)

                if valeursAuxNoeuds:
                    resultat_n = self.__InterpolationAuxNoeuds(resultat_e)
                    return resultat_n.reshape(Nn, -1)
                else:
                    return resultat_e.reshape(Ne, -1)
            
            else:

                Nn = self.__mesh.Nn

                if "d" in option or "amplitude" in option:
                    resultat_ddl = self.displacement
                elif "v" in option:
                    resultat_ddl = self.speed
                elif "a" in option:
                    resultat_ddl = self.accel

                resultat_ddl = resultat_ddl.reshape(Nn, -1)

                index = self.__Get_indexe_option(option)
                
                if valeursAuxNoeuds:

                    if option == "amplitude":
                        return np.sqrt(np.sum(resultat_ddl**2,axis=1))
                    else:
                        if len(resultat_ddl.shape) > 1:
                            return resultat_ddl[:,index]
                        else:
                            return resultat_ddl.reshape(-1)
                            
                else:

                    # recupere pour chaque element les valeurs de ses noeuds
                    resultat_e_n = self.__mesh.Localises_sol_e(resultat_ddl)
                    resultat_e = resultat_e_n.mean(axis=1)

                    if option == "amplitude":
                        return np.sqrt(np.sum(resultat_e**2, axis=1))
                    elif option in ["speed", "accel"]:
                        return resultat_e.reshape(-1)
                    else:
                        if len(resultat_e.shape) > 1:
                            return resultat_e[:,index]
                        else:
                            return resultat_e.reshape(-1)

        elif problemType == "beam":

            if option == "beamDisplacement":
                return self.beamDisplacement.copy()
        
            if option == 'coordoDef':
                return self.GetCoordUglob()

            if option in ["fx","fy","fz","cx","cy","cz"]:

                force = np.array(self.__Kbeam.dot(self.__beamDisplacement))
                force_redim = force.reshape(self.mesh.Nn, -1)
                index = self.__Get_indexe_option(option)
                resultat_ddl = force_redim[:, index]

            else:

                resultat_ddl = self.beamDisplacement
                resultat_ddl = resultat_ddl.reshape((Nn,-1))

            index = self.__Get_indexe_option(option)


            # Deformation et contraintes pour chaque element et chaque points de gauss        
            Epsilon_e_pg = self.__Calc_Epsilon_e_pg(self.beamDisplacement)
            Sigma_e_pg = self.__Calc_Sigma_e_pg(Epsilon_e_pg)

            if option == "Stress":
                return np.mean(Sigma_e_pg, axis=1)


            if valeursAuxNoeuds:
                if option == "amplitude":
                    return np.sqrt(np.sum(resultat_ddl,axis=1))
                else:
                    if len(resultat_ddl.shape) > 1:
                        return resultat_ddl[:,index]
                    else:
                        return resultat_ddl.reshape(-1)
            else:
                # recupere pour chaque element les valeurs de ses noeuds
                    resultat_e_n = self.__mesh.Localises_sol_e(resultat_ddl)
                    resultat_e = resultat_e_n.mean(axis=1)

                    if option == "amplitude":
                        return np.sqrt(np.sum(resultat_e**2, axis=1))
                    elif option in ["speed", "accel"]:
                        return resultat_e
                    else:
                        if len(resultat_ddl.shape) > 1:
                            return resultat_e[:,index]
                        else:
                            return resultat_e.reshape(-1)


        else:

            raise "Aucun résultat pour le modèle renseigné"
    
    def __InterpolationAuxNoeuds(self, resultat_e: np.ndarray):
        """Pour chaque noeuds on récupère les valeurs des élements autour de lui pour on en fait la moyenne
        """

        # tic = TicTac()

        Ne = self.__mesh.Ne
        Nn = self.__mesh.Nn

        if len(resultat_e.shape) == 1:
            resultat_e = resultat_e.reshape(Ne,1)
            isDim1 = True
        else:
            isDim1 = False
        
        Ncolonnes = resultat_e.shape[1]

        resultat_n = np.zeros((Nn, Ncolonnes))

        for c in range(Ncolonnes):

            valeurs_e = resultat_e[:, c]

            connect_n_e = self.__mesh.connect_n_e
            nombreApparition = np.array(np.sum(connect_n_e, axis=1)).reshape(self.__mesh.Nn,1)
            valeurs_n_e = connect_n_e.dot(valeurs_e.reshape(self.__mesh.Ne,1))
            valeurs_n = valeurs_n_e/nombreApparition

            resultat_n[:,c] = valeurs_n.reshape(-1)

        # tic.Tac("Affichage","Affichage des figures", plotResult)

        if isDim1:
            return resultat_n.reshape(-1)
        else:
            return resultat_n

    def Resume(self, verbosity=True):

        resume = Affichage.NouvelleSection("Maillage", False)
        resume += self.mesh.Resume(False)

        resume += Affichage.NouvelleSection("Materiau", False)
        resume += '\n' + self.materiau.Resume(False)

        resume += Affichage.NouvelleSection("Resultats", False)
        if self.materiau.isDamaged:
            resumeChargement = self.resumeChargement
            if resumeChargement == "":
                resume += "\nChargement non renseigné"
            else:
                resume += '\n' + resumeChargement

            resumelastIter = self.resumeIter
            if resumelastIter == "":
                resume += "\nLe résumé de l'itération n'est pas disponible"
            else:
                resume += '\n\n' + resumelastIter
        else:
            resume += self.ResumeResultats(False)

        resume += Affichage.NouvelleSection("Temps", False)
        resume += Tic.getResume(False)

        if verbosity: print(resume)

        return resume

    def ResumeResultats(self, verbosity=True):
        """Ecrit un résumé de la simulation dans le terminal"""

        resume = ""

        if not self.VerificationOption("Wdef"):
            return
        
        Wdef = self.Get_Resultat("Wdef")
        resume += f"\nW def = {Wdef:.3f} N.mm"
        
        Svm = self.Get_Resultat("Svm", valeursAuxNoeuds=False)
        resume += f"\n\nSvm max = {Svm.max():.3f} MPa"

        # Affichage des déplacements
        dx = self.Get_Resultat("dx", valeursAuxNoeuds=True)
        resume += f"\n\nUx max = {dx.max():.6f} mm"
        resume += f"\nUx min = {dx.min():.6f} mm"

        dy = self.Get_Resultat("dy", valeursAuxNoeuds=True)
        resume += f"\n\nUy max = {dy.max():.6f} mm"
        resume += f"\nUy min = {dy.min():.6f} mm"

        if self.__dim == 3:
            dz = self.Get_Resultat("dz", valeursAuxNoeuds=True)
            resume += f"\n\nUz max = {dz.max():.6f} mm"
            resume += f"\nUz min = {dz.min():.6f} mm"

        if verbosity: print(resume)

        return resume
    
    def GetCoordUglob(self):
        """Renvoie les déplacements sous la forme [dx, dy, dz] (Nn,3)        """

        Nn = self.__mesh.Nn
        dim = self.__dim
        problemType = self.__problemType

        if problemType in ["displacement","beam","damage"]:

            if problemType in ["displacement","damage"]:
                Uglob = self.__displacement
            else:
                Uglob = self.__beamDisplacement
                listDim = np.arange(dim)

            coordo = Uglob.reshape((Nn,-1))
           
            if problemType in ["displacement","damage"]:
                if dim == 2:
                    coordo = np.append(coordo, np.zeros((Nn,1)), axis=1)
            else:
                coordo = coordo[:, listDim]

                if self.dim == 1:
                    # Ici on rajoute deux colonnes
                    coordo = np.append(coordo, np.zeros((Nn,1)), axis=1)
                    coordo = np.append(coordo, np.zeros((Nn,1)), axis=1)
                elif self.dim == 2:
                    # Ici on rajoute 1 colonne
                    coordo = np.append(coordo, np.zeros((Nn,1)), axis=1)

            return coordo
        else:
            return None