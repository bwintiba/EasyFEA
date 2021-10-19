from typing import cast

import scipy.sparse as sp
from scipy.sparse.linalg import inv
import numpy as np
import os
import time
from class_ModelGmsh import ModelGmsh

from class_Noeud import Noeud
from class_Element import Element
from class_Mesh import Mesh
from class_Materiau import Materiau

class Simu:
    
    def __init__(self, dim: int,mesh: Mesh, materiau: Materiau, verbosity=True):
        """Creation d'une simulation

        Parameters
        ----------
        dim : int
            Dimension de la simulation 2D ou 3D
        verbosity : bool, optional
            La simulation ecrit tout les details de commande dans la console, by default False
        """
        
        # Vérification des valeurs
        assert dim == 2 or dim == 3, "Dimesion compris entre 2D et 3D"
        assert isinstance(mesh, Mesh) and mesh.get_dim() == dim, "Doit etre un maillage et doit avoir la meme dimension que dim"
        assert isinstance(materiau, Materiau) and materiau.get_dim() == dim, "Doit etre un materiau et doit avoir la meme dimension que dim"


        self.__dim = dim
      
        self.__verbosity = verbosity
        
        self.__mesh = mesh
        
        self.__materiau = materiau
        
        self.resultats = {}
    
    def Assemblage(self, epaisseur=0):
        """Construit Kglobal

        mettre en option u ou d ?

        """

        START = time.time()
        
        if self.__dim == 2:        
            assert epaisseur>0,"Doit être supérieur à 0"

        taille = self.__mesh.get_Nn()*self.__dim

        self.__Kglob = np.zeros((taille, taille))
        self.__Fglob = np.zeros(taille)
        
        for e in self.__mesh.elements:            
            e = cast(Element, e)
            
            Ke = e.ConstruitKe(self.__materiau.C)
            
            test = Ke[:,0]

            # Assemble Ke dans Kglob 
            nPe = e.nPe
            vect = e.assembly
            i = 0
            while i<nPe*self.__dim:
                ligne = vect[i] 
                j=0
                while j<nPe*self.__dim:
                    colonne = vect[j]
                    
                    if self.__dim == 2:
                        self.__Kglob[ligne, colonne] += epaisseur * Ke[i, j]
                    elif self.__dim ==3:
                        self.__Kglob[ligne, colonne] += Ke[i, j]
                    j += 1                                  
                i += 1
           
            # # todo a essayer
            # Kglob = np.zeros((taille, taille))            
            # vect = e.assembly                                
            # if self.dim == 2:
            #     K1 = self.__Kglob
            #     K2 = self.__Kglob[vect,:][:,vect]                 
            #     # Kglob[vect,:][:,vect] += Kglob[vect,:][:,vect] + epaisseur * Ke[:,:]
            #     Kglob[vect,vect] += Ke
            #     pass
            # elif self.dim == 3:    
            #     Kglob[vect,:][:,vect] = Kglob[vect,:][:,vect] + Ke
                
        

            
        
        END = START - time.time()
        if self.__verbosity:
            print("\nAssemblage ({:.3f} s)".format(np.abs(END)))


    def ConstruitH(self, d, u):
        # Pour chaque point de gauss de tout les elements du maillage on va calculer phi+

        pass



    def ConditionEnForce(self, noeuds=[], direction="", force=0):
        START = time.time()
        
        nbn = len(noeuds)
        for n in noeuds:
            n = cast(Noeud, n)
            
            if direction == "X":
                ligne = n.id * self.__dim
                
            if direction == "Y":
                ligne = n.id * self.__dim + 1
                
            if direction == "Z":
                assert self.__dim == 3,"Une étude 2D ne permet pas d'appliquer des forces suivant Z"
                ligne = n.id * self.__dim + 2
                
            self.__Fglob[ligne] += force/nbn
            
        END = START - time.time()
        if self.__verbosity:
            print("\nCondition en force ({:.3f} s)".format(np.abs(END)))

    def ConditionEnDeplacement(self, noeuds=[], direction="", deplacement=0):
        START = time.time()
               
        for n in noeuds:
            n = cast(Noeud, n)
            
            if direction == "X":
                ligne = n.id * self.__dim
                
            if direction == "Y":
                ligne = n.id * self.__dim + 1
                
            if direction == "Z":
                ligne = n.id * self.__dim + 2
            
            self.__Fglob[ligne] = deplacement
            self.__Kglob[ligne,:] = 0.0
            self.__Kglob[ligne, ligne] = 1
            
            
        END = START - time.time()
        if self.__verbosity:
            print("\nCondition en deplacement ({:.3f} s)".format(np.abs(END)))   

    def Solve(self):
        START = time.time()
        
        # Transformatoion en matrice creuse
        self.__Kglob = sp.csc_matrix(self.__Kglob)
        self.__Fglob = sp.lil_matrix(self.__Fglob).T
        
        # Résolution 
        Uglob = inv(self.__Kglob).dot(self.__Fglob)
        
        # Récupération des données
        self.resultats["Wdef"] = 1/2 * Uglob.T.dot(self.__Kglob).dot(Uglob).data[0]

        # Récupère les déplacements

        Uglob = Uglob.toarray()
                
        dx = []
        dy = []
        dz = []

        for n in self.__mesh.noeuds:
            n = cast(Noeud, n)
            
            idNoeud = n.id 
            if self.__dim == 2:
                dx.append(Uglob[idNoeud * 2][0])
                dy.append(Uglob[idNoeud * 2 + 1][0])
            elif self.__dim == 3:
                dx.append(Uglob[idNoeud * 3][0])
                dy.append(Uglob[idNoeud * 3 + 1][0])
                dz.append(Uglob[idNoeud * 3 + 2][0])
                
        dx  = np.array(dx)
        dy  = np.array(dy)
        dz  = np.array(dz)
        
        self.resultats["dx_n"] = dx
        self.resultats["dy_n"] = dy        
        if self.__dim == 3:
            self.resultats["dz_n"] = dz

        # Construit nouvelle coordo
        deplacementCoordo = []
        if self.__dim == 2:
            deplacementCoordo = np.array([dx, dy, np.zeros(self.__mesh.Nn)]).T
        elif self.__dim == 3:
            deplacementCoordo = np.array([dx, dy, dz]).T
        
        self.resultats["deplacementCoordo"] = deplacementCoordo
        
        self.__ExtrapolationAuxElements(deplacementCoordo)

        self.__ExtrapolationAuxNoeuds(dx, dy, dz)        
        
        END = START - time.time()
        if self.__verbosity:
            print("\nRésolution ({:.3f} s)".format(np.abs(END)))

    
    def __ExtrapolationAuxElements(self, deplacementCoordo: np.ndarray):
        
        # Vecteurs pour chaque element
        list_dx_e = []
        list_dy_e = []
        list_dz_e = []
        
        list_Exx_e = []
        list_Eyy_e = []
        list_Ezz_e = []
        list_Exy_e = []
        list_Eyz_e = []
        list_Exz_e = []
        
        list_Sxx_e = []
        list_Syy_e = []
        list_Szz_e = []
        list_Sxy_e = []
        list_Syz_e = []
        list_Sxz_e = []

        list_Svm_e = []
        
        # Pour chaque element on va caluler ces valeurs en déplacement deformation et contraintes
        for e in self.__mesh.elements:
            e = cast(Element, e)

            dx_n = []
            dy_n = []
            dz_n = []
            
            Exx_n = []
            Eyy_n = []
            Ezz_n = []
            Exy_n = []
            Eyz_n = []
            Exz_n = []
            
            Sxx_n = []
            Syy_n = []
            Szz_n = []
            Sxy_n = []
            Syz_n = []
            Sxz_n = []
            
            Svm_n = []

            # Construit ue
            ue = []
            for n in e.noeuds:
                n = cast(Noeud, n)
                id = n.id
                
                # Pour chaque noeud on récupère dx, dy, dz
                dx = deplacementCoordo[id,0]
                dy = deplacementCoordo[id,1]
                dz = deplacementCoordo[id,2]
                
                # On ajoute dans les listes
                ue.append(dx), dx_n.append(dx)
                ue.append(dy), dy_n.append(dy)
                
                if self.__dim == 3:                    
                    ue.append(dz), dz_n.append(dz)

            

            ue = np.array(ue)

            # Pour chaques matrice Be aux Noeuds de l'element on va calculer deformation puis contraintes

            for B in e.listBeAuNoeuds:
                vect_Epsilon = B.dot(ue)
                vect_Sigma = self.__materiau.C.dot(vect_Epsilon)
                
                if self.__dim == 2:                
                    Exx_n.append(vect_Epsilon[0])
                    Eyy_n.append(vect_Epsilon[1])
                    Exy_n.append(vect_Epsilon[2])
                    
                    Sxx = vect_Sigma[0]
                    Syy = vect_Sigma[1]
                    Sxy = vect_Sigma[2]                    
                    
                    Sxx_n.append(Sxx)
                    Syy_n.append(Syy)
                    Sxy_n.append(Sxy)
                    Svm_n.append(np.sqrt(Sxx**2+Syy**2-Sxx*Syy+3*Sxy**2))
                    
                elif self.__dim == 3:
                    Exx_n.append(vect_Epsilon[0]) 
                    Eyy_n.append(vect_Epsilon[1])
                    Ezz_n.append(vect_Epsilon[2])                    
                    Exy_n.append(vect_Epsilon[3])
                    Eyz_n.append(vect_Epsilon[4])
                    Exz_n.append(vect_Epsilon[5])
                    
                    Sxx = vect_Sigma[0]
                    Syy = vect_Sigma[1]
                    Szz = vect_Sigma[2]                    
                    Sxy = vect_Sigma[3]
                    Syz = vect_Sigma[4]
                    Sxz = vect_Sigma[5]
                    
                    Sxx_n.append(Sxx)
                    Syy_n.append(Syy)
                    Szz_n.append(Szz)
                    
                    Sxy_n.append(Sxy)
                    Syz_n.append(Syz)
                    Sxz_n.append(Sxz)
                    
                    Svm = np.sqrt(((Sxx-Syy)**2+(Syy-Szz)**2+(Szz-Sxx)**2+6*(Sxy**2+Syz**2+Sxz**2))/2)
                    
                    Svm_n.append(Svm)
            

            # Récupère la moyenne des résultats aux noeuds
            list_dx_e.append(np.mean(dx_n))
            list_dy_e.append(np.mean(dy_n))

            list_Exx_e.append(np.mean(Exx_n))
            list_Eyy_e.append(np.mean(Eyy_n))
            list_Exy_e.append(np.mean(Exy_n))

            list_Sxx_e.append(np.mean(Sxx_n))
            list_Syy_e.append(np.mean(Syy_n))
            list_Sxy_e.append(np.mean(Sxy_n))

            list_Svm_e.append(np.mean(Svm_n))

            if self.__dim == 3:
                list_dz_e.append(np.mean(dz_n))

                list_Ezz_e.append(np.mean(Ezz_n))
                list_Eyz_e.append(np.mean(Eyz_n))
                list_Exz_e.append(np.mean(Exz_n))

                list_Szz_e.append(np.mean(Szz_n))
                list_Syz_e.append(np.mean(Syz_n))
                list_Sxz_e.append(np.mean(Sxz_n))

        self.resultats["dx_e"] = list_dx_e
        self.resultats["dy_e"] = list_dy_e

        self.resultats["Exx_e"] = list_Exx_e
        self.resultats["Eyy_e"] = list_Eyy_e
        self.resultats["Exy_e"] = list_Exy_e

        self.resultats["Sxx_e"] = list_Sxx_e
        self.resultats["Syy_e"] = list_Syy_e
        self.resultats["Sxy_e"] = list_Sxy_e

        self.resultats["Svm_e"] = list_Svm_e
        
        if self.__dim == 3: 
            self.resultats["dz_e"] = list_dz_e

            self.resultats["Ezz_e"] = list_Ezz_e
            self.resultats["Eyz_e"] = list_Eyz_e
            self.resultats["Exz_e"] = list_Exz_e
            
            self.resultats["Szz_e"] = list_Szz_e
            self.resultats["Syz_e"] = list_Syz_e
            self.resultats["Sxz_e"] = list_Sxz_e

    def __ExtrapolationAuxNoeuds(self, dx, dy, dz, option = 'mean'):
        # Extrapolation des valeurs aux noeuds  
        
        Exx_n = []
        Eyy_n = []
        Ezz_n = []
        Exy_n = []
        Eyz_n = []
        Exz_n = []
        
        Sxx_n = []
        Syy_n = []
        Szz_n = []
        Sxy_n = []
        Syz_n = []
        Sxz_n = []
        
        Svm_n = []
        
        for noeud in self.__mesh.noeuds:
            noeud = cast(Noeud, noeud)
            
            list_Exx = []
            list_Eyy = []
            list_Exy = []
            
            list_Sxx = []
            list_Syy = []
            list_Sxy = []
            
            list_Svm = []      
                
            if self.__dim == 3:                
                list_Ezz = []
                list_Eyz = []
                list_Exz = []
                                
                list_Szz = []                
                list_Syz = []
                list_Sxz = []
                        
            for element in noeud.elements:
                element = cast(Element, element)
                            
                listIdNoeuds = list(self.__mesh.connect[element.id])
                index = listIdNoeuds.index(noeud.id)
                BeDuNoeud = element.listBeAuNoeuds[index]
                
                # Construit ue
                deplacement = []
                for noeudDeLelement in element.noeuds:
                    noeudDeLelement = cast(Noeud, noeudDeLelement)
                    
                    if self.__dim == 2:
                        deplacement.append(dx[noeudDeLelement.id])
                        deplacement.append(dy[noeudDeLelement.id])
                    if self.__dim == 3:
                        deplacement.append(dx[noeudDeLelement.id])
                        deplacement.append(dy[noeudDeLelement.id])
                        deplacement.append(dz[noeudDeLelement.id])
                        
                deplacement = np.array(deplacement)
                
                vect_Epsilon = BeDuNoeud.dot(deplacement)
                vect_Sigma = self.__materiau.C.dot(vect_Epsilon)
                
                if self.__dim == 2:                
                    list_Exx.append(vect_Epsilon[0])
                    list_Eyy.append(vect_Epsilon[1])
                    list_Exy.append(vect_Epsilon[2])
                    
                    Sxx = vect_Sigma[0]
                    Syy = vect_Sigma[1]
                    Sxy = vect_Sigma[2]                    
                    
                    list_Sxx.append(Sxx)
                    list_Syy.append(Syy)
                    list_Sxy.append(Sxy)
                    list_Svm.append(np.sqrt(Sxx**2+Syy**2-Sxx*Syy+3*Sxy**2))
                    
                elif self.__dim == 3:
                    list_Exx.append(vect_Epsilon[0]) 
                    list_Eyy.append(vect_Epsilon[1])
                    list_Ezz.append(vect_Epsilon[2])                    
                    list_Exy.append(vect_Epsilon[3])
                    list_Eyz.append(vect_Epsilon[4])
                    list_Exz.append(vect_Epsilon[5])
                    
                    Sxx = vect_Sigma[0]
                    Syy = vect_Sigma[1]
                    Szz = vect_Sigma[2]                    
                    Sxy = vect_Sigma[3]
                    Syz = vect_Sigma[4]
                    Sxz = vect_Sigma[5]
                    
                    list_Sxx.append(Sxx)
                    list_Syy.append(Syy)
                    list_Szz.append(Szz)
                    
                    list_Sxy.append(Sxy)
                    list_Syz.append(Syz)
                    list_Sxz.append(Sxz)
                    
                    Svm = np.sqrt(((Sxx-Syy)**2+(Syy-Szz)**2+(Szz-Sxx)**2+6*(Sxy**2+Syz**2+Sxz**2))/2)
                    
                    list_Svm.append(Svm)
            
            def TrieValeurs(source:list, option: str):
                # Verifie si il ny a pas une valeur bizzare
                max = np.max(source)
                min = np.min(source)
                mean = np.mean(source)
                    
                valeurAuNoeud = 0
                if option == 'max':
                    valeurAuNoeud = max
                elif option == 'min':
                    valeurAuNoeud = min
                elif option == 'mean':
                    valeurAuNoeud = mean
                elif option == 'first':
                    valeurAuNoeud = source[0]
                    
                return valeurAuNoeud
            
            Exx_n.append(TrieValeurs(list_Exx, option))
            Eyy_n.append(TrieValeurs(list_Eyy, option)) 
            Exy_n.append(TrieValeurs(list_Exy, option))
            
            Sxx_n.append(TrieValeurs(list_Sxx, option))
            Syy_n.append(TrieValeurs(list_Syy, option))
            Sxy_n.append(TrieValeurs(list_Sxy, option))
            
            Svm_n.append(TrieValeurs(list_Svm, option))
        
            if self.__dim == 3:
                Ezz_n.append(TrieValeurs(list_Ezz, option))
                Eyz_n.append(TrieValeurs(list_Eyz, option))
                Exz_n.append(TrieValeurs(list_Exz, option))
                
                Szz_n.append(TrieValeurs(list_Szz, option))
                Syz_n.append(TrieValeurs(list_Syz, option))
                Sxz_n.append(TrieValeurs(list_Sxz, option))
            
        
        self.resultats["Exx_n"] = Exx_n
        self.resultats["Eyy_n"] = Eyy_n
        self.resultats["Exy_n"] = Exy_n
        self.resultats["Sxx_n"] = Sxx_n
        self.resultats["Syy_n"] = Syy_n
        self.resultats["Sxy_n"] = Sxy_n      
        self.resultats["Svm_n"] = Svm_n
        
        if self.__dim == 3:            
            self.resultats["Ezz_n"] = Ezz_n
            self.resultats["Eyz_n"] = Eyz_n
            self.resultats["Exz_n"] = Exz_n
            
            self.resultats["Szz_n"] = Szz_n
            self.resultats["Syz_n"] = Syz_n
            self.resultats["Sxz_n"] = Sxz_n
    
    
                
    
         
# ====================================

import unittest
import os

class Test_Simu(unittest.TestCase):
    
    def CreationDesSimusElastique2D(self):
        
        dim = 2

        # Paramètres géométrie
        L = 120;  #mm
        h = 13;    
        b = 13

        # Charge a appliquer
        P = -800 #N

        # Paramètres maillage
        taille = L

        materiau = Materiau(dim)

        self.simulations2DElastique = []

        # Pour chaque type d'element 2D
        for type in ModelGmsh.get_typesMaillage2D():
            # Construction du modele et du maillage 
            modelGmsh = ModelGmsh(dim, organisationMaillage=True, typeElement=type, tailleElement=taille, verbosity=False)

            (coordo, connect) = modelGmsh.ConstructionRectangle(L, h)
            mesh = Mesh(dim, coordo, connect)

            simu = Simu(dim, mesh, materiau, verbosity=False)

            simu.Assemblage(epaisseur=b)

            noeud_en_L = []
            noeud_en_0 = []
            for n in mesh.noeuds:            
                    n = cast(Noeud, n)
                    if n.coordo[0] == L:
                            noeud_en_L.append(n)
                    if n.coordo[0] == 0:
                            noeud_en_0.append(n)

            simu.ConditionEnForce(noeuds=noeud_en_L, force=P, direction="Y")

            simu.ConditionEnDeplacement(noeuds=noeud_en_0, deplacement=0, direction="X")
            simu.ConditionEnDeplacement(noeuds=noeud_en_0, deplacement=0, direction="Y")

            self.simulations2DElastique.append(simu)

    def CreationDesSimusElastique3D(self):

        fichier = "part.stp"

        dim = 3

        # Paramètres géométrie
        L = 120  #mm
        h = 13    
        b = 13

        P = -800 #N

        # Paramètres maillage        
        taille = L

        materiau = Materiau(dim)
        
        self.simulations3DElastique = []

        for type in ModelGmsh.get_typesMaillage3D():
            modelGmsh = ModelGmsh(dim, organisationMaillage=True, typeElement=type, tailleElement=taille, gmshVerbosity=False, affichageGmsh=False, verbosity=False)

            (coordo, connect) = modelGmsh.Importation3D(fichier)
            mesh = Mesh(dim, coordo, connect)

            simu = Simu(dim,mesh, materiau, verbosity=False)

            simu.Assemblage(epaisseur=b)

            noeuds_en_L = []
            noeuds_en_0 = []
            for n in mesh.noeuds:
                    n = cast(Noeud, n)        
                    if n.coordo[0] == L:
                            noeuds_en_L.append(n)
                    if n.coordo[0] == 0:
                            noeuds_en_0.append(n)

            simu.ConditionEnForce(noeuds=noeuds_en_L, force=P, direction="Z")

            simu.ConditionEnDeplacement(noeuds=noeuds_en_0, deplacement=0, direction="X")
            simu.ConditionEnDeplacement(noeuds=noeuds_en_0, deplacement=0, direction="Y")
            simu.ConditionEnDeplacement(noeuds=noeuds_en_0, deplacement=0, direction="Z")

            self.simulations3DElastique.append(simu)
    
    def setUp(self):
        self.CreationDesSimusElastique2D()
        self.CreationDesSimusElastique3D()  

    def test_ResolutionDesSimulationsElastique2D(self):
        # Pour chaque type de maillage on simule
        for simu in self.simulations2DElastique:
            simu = cast(Simu, simu)
            simu.Solve()

    def test_ResolutionDesSimulationsElastique3D(self):
        # Pour chaque type de maillage on simule
        for simu in self.simulations3DElastique:
            simu = cast(Simu, simu)
            simu.Solve()


if __name__ == '__main__':        
    try:
        os.system("cls")    #nettoie terminal
        unittest.main(verbosity=2)    
    except:
        print("")    

        
            
