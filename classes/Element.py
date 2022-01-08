import numpy as np
from numpy.core.fromnumeric import shape

class Element:

    @staticmethod
    def get_Types(dim):
        if dim == 2:
            return Element.__listElement2D.copy()
        else:
            return Element.__listElement3D.copy()

    __listElement2D = ["TRI3", "TRI6", "QUAD4", "QUAD8"]    
    __listElement3D = ["TETRA4"]

    def get_nbFaces(self):
        if self.__dim == 2:
            return 1
        else:
            # TETRA4
            if self.nPe == 4:
                return 4

    def __get_ElementType(self):
        """Renvoie le type de l'élément en fonction du nombre de noeuds par élement
        """        
        if self.__dim == 2:        
            switch = {
                3 : "TRI3",
                6 : "TRI6",
                4 : "QUAD4",
                8 : "QUAD8",
            }                
            return switch[self.nPe]
        if self.__dim == 3:
            switch = {
                4 : "TETRA4",                
            }                
            return switch[self.nPe]
    type = property(__get_ElementType) 

    def __get_nPg(self):
        return self.gauss.shape[0]
    nPg = property(__get_nPg)

    def __init__(self, dim: int, nPe: int):
        """Constructeur d'element, on construit Be et le jacobien !

        Parameters
        ----------
        dim : int
            Numéro de l'élement (>=0)
        nPe : int
            Nombre de noeud par element
        """

        assert dim in [2,3], "Dimesion compris entre 2D et 3D"
        
        # Création des variables de la classe        
        self.__dim = dim
        
        self.nPe = nPe
        
        # ksi eta poid
        self.gauss = np.zeros((0,3))

        # [N1 0 ... Nn 0
        #  0 N1 ... 0 Nn]
        self.N_rigi_pg = []

        # [N1 ... Nn]
        self.N_mass_pg = []

        # [N1,ksi ... Nn,ksi
        #  N1,eta ... Nn,eta]
        self.dN_pg = []
                     
        self.__Construit_B_N()

    def __Construit_B_N(self):
        
        # Construit les fonctions de forme et leur dérivée pour l'element de référence

        if self.__dim == 2:        
            # Triangle à 3 noeuds ou 6 noeuds Application linéaire
            if self.nPe == 3 or self.nPe == 6:
                self.__Construit_B_N_Triangle()
            elif self.nPe == 4 or self.nPe == 8:
                self.__Construit_B_N_Quadrangle()
        elif self.__dim == 3:
            if self.nPe == 4:
                self.__Construit_B_N_Tetraedre()

    def __Construit_B_N_Triangle(self):

        # TRI3
        if self.nPe == 3:  
            
            # Points de gauss
            ksi = 1/3
            eta = 1/3
            poid = 1/2
            self.gauss = np.array([ksi, eta, poid]).reshape((1,3))

            # Calcul N aux points de gauss
            N1t = 1-ksi-eta
            N2t = ksi
            N3t = eta
            Ntild = [N1t, N2t, N3t]

            self.N_rigi_pg.append(self.__ConstruitN(Ntild))

            self.N_mass_pg.append(np.array(Ntild))

            self.dN_pg.append(np.array([[-1, 1, 0],[-1, 0, 1]]))

        # TRI6  
        if self.nPe == 6:
            
            # Points de gauss
            ksis = [1/6, 2/3, 1/6]
            etas = [1/6, 1/6, 2/3]
            poids = [1/6] * 3
            self.gauss = np.array([ksis, etas, poids]).T
            
            def Construit_Ntild(ksi, eta):
                # Code aster (Fonctions de forme et points d'intégration des élé[...])
                N1t = -(1-ksi-eta)*(1-2*(1-ksi-eta))
                N2t = -ksi*(1-2*ksi)
                N3t = -eta*(1-2*eta)
                N4t = 4*ksi*(1-ksi-eta)
                N5t = 4*ksi*eta
                N6t = 4*eta*(1-ksi-eta)
                return [N1t, N2t, N3t, N4t, N5t, N6t]

            def Construit_dNtild(ksi, eta):
                dN1t = np.array([4*ksi+4*eta-3] *2)
                dN2t = np.array([4*ksi-1, 0])
                dN3t = np.array([0, 4*eta-1])
                dN4t = np.array([4-8*ksi-4*eta, -4*ksi])
                dN5t = np.array([4*eta, 4*ksi])
                dN6t = np.array([-4*eta, 4-4*ksi-8*eta])
                return np.array([dN1t, dN2t, dN3t, dN4t, dN5t, dN6t]).T
            
            for pg in range(len(ksis)):
                
                ksi = ksis[pg] 
                eta = etas[pg]
                
                Ntild = Construit_Ntild(ksi, eta)                
                
                N_rigi = self.__ConstruitN(Ntild)
                self.N_rigi_pg.append(N_rigi)

                N_mass = self.__ConstruitN(Ntild, vecteur=False)
                self.N_mass_pg.append(N_mass)
                
                dNtild = Construit_dNtild(ksi, eta)
                self.dN_pg.append(dNtild)

    def __Construit_B_N_Quadrangle(self):
        """Construit la matrice Be d'un element quadrillatère
        """
        if self.nPe == 4:
            
            # Points de gauss
            UnSurRacine3 = 1/np.sqrt(3) 
            ksis = [-UnSurRacine3, UnSurRacine3, UnSurRacine3, -UnSurRacine3]
            etas = [-UnSurRacine3, -UnSurRacine3, UnSurRacine3, UnSurRacine3]
            poids = [1]*4
            self.gauss = np.array([ksis, etas, poids]).T

            def Construit_Ntild(ksi, eta):
                N1t = (1-ksi)*(1-eta)/4
                N2t = (1+ksi)*(1-eta)/4
                N3t = (1+ksi)*(1+eta)/4
                N4t = (1-ksi)*(1+eta)/4
                return [N1t, N2t, N3t, N4t]
            
            def Construit_dNtild(ksi, eta):
                dN1t = np.array([(eta-1)/4, (ksi-1)/4])
                dN2t = np.array([(1-eta)/4, (-ksi-1)/4])
                dN3t = np.array([(1+eta)/4, (1+ksi)/4])
                dN4t = np.array([(-eta-1)/4, (1-ksi)/4])                
                return np.array([dN1t, dN2t, dN3t, dN4t]).T
            
            for pg in range(len(ksis)):
                
                ksi = ksis[pg] 
                eta = etas[pg]
                
                Ntild = Construit_Ntild(ksi, eta)
                
                N_rigi = self.__ConstruitN(Ntild)
                self.N_rigi_pg.append(N_rigi)

                N_mass = self.__ConstruitN(Ntild, vecteur=False)                
                self.N_mass_pg.append(N_mass)

                dNtild = Construit_dNtild(ksi, eta)
                self.dN_pg.append(dNtild)            
              
        elif self.nPe ==8:
            
            # Points de gauss
            UnSurRacine3 = 1/np.sqrt(3) 
            ksis = [-UnSurRacine3, UnSurRacine3, UnSurRacine3, -UnSurRacine3]
            etas = [-UnSurRacine3, -UnSurRacine3, UnSurRacine3, UnSurRacine3]
            poids = [1]*4
            self.gauss = np.array([ksis, etas, poids]).T

            def Construit_Ntild(Ksi, eta):
                N1t = (1-ksi)*(1-eta)*(-1-ksi-eta)/4
                N2t = (1+ksi)*(1-eta)*(-1+ksi-eta)/4
                N3t = (1+ksi)*(1+eta)*(-1+ksi+eta)/4
                N4t = (1-ksi)*(1+eta)*(-1-ksi+eta)/4
                N5t = (1-ksi**2)*(1-eta)/2
                N6t = (1+ksi)*(1-eta**2)/2
                N7t = (1-ksi**2)*(1+eta)/2
                N8t = (1-ksi)*(1-eta**2)/2
                return [N1t, N2t, N3t, N4t, N5t, N6t, N7t, N8t]

            def Construit_dNtild(ksi, eta):
                dN1t = np.array([(1-eta)*(2*ksi+eta)/4, (1-ksi)*(ksi+2*eta)/4])
                dN2t = np.array([(1-eta)*(2*ksi-eta)/4, -(1+ksi)*(ksi-2*eta)/4])
                dN3t = np.array([(1+eta)*(2*ksi+eta)/4, (1+ksi)*(ksi+2*eta)/4])
                dN4t = np.array([-(1+eta)*(-2*ksi+eta)/4, (1-ksi)*(-ksi+2*eta)/4])
                dN5t = np.array([-ksi*(1-eta), -(1-ksi**2)/2])
                dN6t = np.array([(1-eta**2)/2, -eta*(1+ksi)])
                dN7t = np.array([-ksi*(1+eta), (1-ksi**2)/2])                
                dN8t = np.array([-(1-eta**2)/2, -eta*(1-ksi)])
                                
                return np.array([dN1t, dN2t, dN3t, dN4t, dN5t, dN6t, dN7t, dN8t]).T

            for pg in range(len(ksis)):
                
                ksi = ksis[pg] 
                eta = etas[pg]
                
                Ntild = Construit_Ntild(ksi, eta)
                
                N_rigi = self.__ConstruitN(Ntild)
                self.N_rigi_pg.append(N_rigi)

                N_mass = self.__ConstruitN(Ntild, vecteur=False)
                self.N_mass_pg.append(N_mass)

                dNtild = Construit_dNtild(ksi, eta)
                self.dN_pg.append(dNtild)
            
    def __Construit_B_N_Tetraedre(self):
        if self.nPe == 4:                       
            
            # Points de gauss
            x = 1/4
            y = 1/4
            z = 1/4
            poid = 1/6
            self.gauss = np.array([x, y, z, poid]).reshape((1,4))

            # Construit Ntild
            N1t = 1-x-y-z
            N2t = x
            N3t = y
            N4t = z            
            Ntild = [N1t, N2t, N3t, N4t]
            
            self.N_rigi_pg.append(self.__ConstruitN(Ntild))

            self.N_mass_pg.append(self.__ConstruitN(Ntild, vecteur=False))

            # Construit dNtild
            dN1t = np.array([-1, -1, -1])
            dN2t = np.array([1, 0, 0])
            dN3t = np.array([0, 1, 0])
            dN4t = np.array([0, 0, 1])
            dNtild = [dN1t, dN2t, dN3t, dN4t]
            self.dN_pg.append(dNtild)
    
    def ConstruitB_pg(self, list_dNtild: list, invF: np.ndarray, vecteur=True):  
        """Construit la matrice Be depuis les fonctions de formes de l'element
        de reference et l'inverserse de la matrice F

        Parameters
        ----------
        list_Ntild : list
            Liste des vecteurs Ntildix et y
        invF : np.ndarray
            Inverse de la matrice F

        Returns
        -------
        np.ndarray
            si dim = 2
            Renvoie une matrice de dim (3,len(list_Ntild)*2)
            
            si dim = 3
            Renvoie une matrice de dim (6,len(list_Ntild)*3)
        """
        
        # list_dNtild = np.array(list_dNtild)
        
        if vecteur:
            if self.__dim == 2:            
                B_pg = np.zeros((3,len(list_dNtild)*2))      

                colonne = 0
                for dNt in list_dNtild:            
                    dNdx = invF[0].dot(dNt)
                    dNdy = invF[1].dot(dNt)
                    
                    B_pg[0, colonne] = dNdx
                    B_pg[1, colonne+1] = dNdy
                    B_pg[2, colonne] = dNdy; B_pg[2, colonne+1] = dNdx    
                    colonne += 2
            elif self.__dim == 3:
                B_pg = np.zeros((6,len(list_dNtild)*3))

                colonne = 0
                for dNt in list_dNtild:            
                    dNdx = invF[0].dot(dNt)
                    dNdy = invF[1].dot(dNt)
                    dNdz = invF[2].dot(dNt)
                    
                    B_pg[0, colonne] = dNdx
                    B_pg[1, colonne+1] = dNdy
                    B_pg[2, colonne+2] = dNdz
                    B_pg[3, colonne] = dNdy; B_pg[3, colonne+1] = dNdx
                    B_pg[4, colonne+1] = dNdz; B_pg[4, colonne+2] = dNdy
                    B_pg[5, colonne] = dNdz; B_pg[5, colonne+2] = dNdx
                    colonne += 3
        else:
            # Construit B comme pour un probleme de thermique
            B_pg = np.zeros((self.__dim, len(list_dNtild)))
            
            for i in range(len(list_dNtild)):
                dNt = list_dNtild[i]
                for j in range(self.__dim):
                    # j=0 dNdx, j=1 dNdy, j=2 dNdz
                    dNdj = invF[j].dot(dNt)
                    B_pg[j, i] = dNdj

        return B_pg
    
    def __ConstruitN(self, list_Ntild: list, vecteur=True):
        """Construit la matrice de fonction de forme

        Parameters
        ----------
        list_Ntild : list des fonctions Ntild
            Fonctions Ntild
        vecteur : bool, optional
            Option qui permet de construire N pour un probleme de déplacement ou un problème thermique, by default True

        Returns
        -------
        ndarray
            Renvoie la matrice Ntild
        """
        if vecteur:
            N_pg = np.zeros((self.__dim, len(list_Ntild)*self.__dim))
            
            colonne = 0
            for nt in list_Ntild:
                for ligne in range(self.__dim):
                    N_pg[ligne, colonne] = nt
                    colonne += 1
        else:
            N_pg = np.zeros((1, len(list_Ntild)))
            colonne = 0
            for nt in list_Ntild:
                N_pg[0, colonne] = nt
                colonne += 1            

        return N_pg

# ====================================

import unittest
import os

class Test_Element(unittest.TestCase):
    
    def setUp(self):
        self.element = Element(1,3)  

    def test_BienCree(self):
        self.assertIsInstance(self.element, Element)        

if __name__ == '__main__':        
    try:
        os.system("cls")    #nettoie terminal
        unittest.main(verbosity=2)    
    except:
        print("")