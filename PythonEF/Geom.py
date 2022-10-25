from typing import List
import numpy as np


class Point:
    """Classe Point"""

    def __init__(self, x=0.0, y=0.0, z=0.0, isOpen=False):
        """Construit un point

        Parameters
        ----------
        x : float, optional
            coordo en x, by default 0.0
        y : float, optional
            coordo en y, by default 0.0
        z : float, optional
            coordo en z, by default 0.0
        isOpen : bool, optional
            le point peut s'ouvrir, by default False
        """
        self.x = x
        self.y = y
        self.z = z
        self.coordo = np.array([x, y, z]).reshape(1,3)
        self.isOpen = isOpen

class Geom:

    def __init__(self, points: List[Point], taille: float, name: str):
        """Construit un objet géométrique

        Parameters
        ----------
        points : List[Point]
            liste de points pour construire l'objet géométrique
        taille : float
            taille de maillage qui sera utilisé pour creer le maillage >= 0
        name : str
            nom de l'objet
        """
        assert taille >= 0
        self.__taille = taille

        self.__points = points

        self.__name = name

    @property
    def taille(self) -> bool:
        """Taille d'element utilisé pour le maillage"""
        return self.__taille

    @property
    def points(self) -> List[Point]:
        """Points utilisés pour construire l'objet"""
        return self.__points

    @property
    def name(self) -> str:
        """Nom de l'objet"""
        return self.__name
        

class Line(Geom):
    """Classe Line"""

    __nbLine = 0

    @staticmethod
    def distance(pt1: Point, pt2: Point) -> float:
        """Calcul la distance entre deux points"""
        length = np.sqrt((pt1.x-pt2.x)**2 + (pt1.y-pt2.y)**2 + (pt1.z-pt2.z)**2)
        return np.abs(length)
    
    @staticmethod
    def get_vecteurUnitaire(pt1: Point, pt2: Point) -> np.ndarray:
        """Construit le vecteur unitaire qui passe entre deux points"""
        length = Line.distance(pt1, pt2)        
        v = np.array([pt2.x-pt1.x, pt2.y-pt1.y, pt2.z-pt1.z])/length
        return v   

    def __init__(self, pt1: Point, pt2: Point, taille=0.0, isOpen=False):
        """Construit une ligne

        Parameters
        ----------
        pt1 : Point
            premier point
        pt2 : Point
            deuxième point
        taille : float, optional
            taille qui sera utilisée pour la construction du maillage, by default 0.0
        """
        self.pt1 = pt1
        self.pt2 = pt2
        self.coordo = np.array([[pt1.x, pt1.y, pt1.z], [pt2.x, pt2.y, pt2.z]]).reshape(2,3)

        self.__isOpen = isOpen

        Line.__nbLine += 1
        name = f"Line{Line.__nbLine}"
        Geom.__init__(self, points=[pt1, pt2], taille=taille, name=name)
    

    @property
    def isOpen(self) -> bool:
        """Renvoie si la ligne peut s'ouvrir pour représenter une fissure"""
        return self.__isOpen
    
    @property
    def vecteurUnitaire(self) -> np.ndarray:
        """Construction du vecteur unitaire pour les deux points de la ligne"""
        return Line.get_vecteurUnitaire(self.pt1, self.pt2)

    @property
    def length(self) -> float:
        """Calcul la longeur de la ligne"""
        return Line.distance(self.pt1, self.pt2)

class Domain(Geom):
    """Classe Domain"""

    __nbDomain = 0

    def __init__(self, pt1: Point, pt2: Point, taille=0.0, isCreux=False):
        """Construit d'un domaine entre 2 points\n
        Ce domaine n'est pas tourné !

        Parameters
        ----------
        pt1 : Point
            point 1
        pt2 : Point
            point 2
        taille : float, optional
            taille qui sera utilisée pour la construction du maillage, by default 0.0
        isCreux : bool, optional
            le domaine est creux, by default False
        """
        self.pt1 = pt1
        self.pt2 = pt2

        self.isCreux = isCreux

        Domain.__nbDomain += 1
        name = f"Domain{Domain.__nbDomain}"
        Geom.__init__(self, points=[pt1, pt2], taille=taille, name=name)

class Circle(Geom):
    """Classe Circle"""

    __nbCircle = 0

    def __init__(self, center: Point, diam: float, taille=0.0, isCreux=True):
        """Construction d'un cercle en fonction de son centre et de son diamètre \n
        Ce cercle sera projeté dans le plan (x,y)

        Parameters
        ----------
        center : Point
            point 1
        diam : float
            diamètre
        taille : float, optional
            taille qui sera utilisée pour la construction du maillage, by default 0.0
        isCreux : bool, optional
            le cercle est creux, by default True
        """
        
        assert diam > 0.0

        self.center = center
        self.diam = diam
        
        self.isCreux = isCreux

        Circle.__nbCircle += 1
        name = f"Circle{Circle.__nbCircle}"
        Geom.__init__(self, points=[center], taille=taille, name=name)

class Section:

    def __init__(self, mesh):
        """Section

        Parameters
        ----------
        mesh : Mesh
            Maillage
        """

        from Mesh import Mesh
        assert isinstance(mesh, Mesh), "Doit être un maillage 2D"

        assert mesh.dim == 2, "Doit être un maillage 2D"
        
        self.__mesh = mesh

    @property
    def mesh(self):
        """Maillage de la section"""
        return self.__mesh

    @property
    def epaisseur(self) -> float:
        """Epaisseur de la section"""
        # ici l'epaisseur est suivant x
        coordo = self.__mesh.coordo
        epaisseur = np.abs(coordo[:,0].max() - coordo[:,0].min())
        return epaisseur
    
    @property
    def hauteur(self) -> float:
        """Hauteur de la section"""
        # ici l'epaisseur est suivant x
        coordo = self.__mesh.coordo
        hauteur = np.abs(coordo[:,1].max() - coordo[:,1].min())
        return hauteur
    
    @property
    def aire(self) -> float:
        """Surface de la section"""
        return self.__mesh.aire

    @property
    def Iy(self) -> float:
        """Moment quadratique de la section suivant y\n
        int_S z^2 dS """
        return self.__mesh.Ix

    @property
    def Iz(self) -> float:
        """Moment quadratique de la section suivant z\n
        int_S y^2 dS """
        return self.__mesh.Iy

    @property
    def Iyz(self) -> float:
        """Moment quadratique de la section suivant yz\n
        int_S y z dS """
        return self.__mesh.Ixy

    @property
    def J(self) -> float:
        """Moment quadratique polaire\n
        J = Iz + Iy
        """
        return self.__mesh.J

