# Copyright (C) 2021-2024 Université Gustave Eiffel. All rights reserved.
# This file is part of the EasyFEA project.
# EasyFEA is distributed under the terms of the GNU General Public License, Version 3 or later, see LICENSE.txt and CREDITS.txt for more information.

from abc import ABC, abstractmethod

class Observable:
    """The observable interface"""

    @property
    def observers(self):
        """Oberservers looking for the observable obect"""
        try:
            return self.__observers
        except AttributeError:
            # here self.__observers has not been created yet
            self.__observers: list[_IObserver] = []
            return self.__observers
    
    def _Add_observer(self, observer) -> None:
        """Add observer."""

        if not isinstance(observer, _IObserver):
            from .Display import myPrintError
            myPrintError(f'observer must be an {_IObserver.__name__}')
            return
        
        if observer not in self.observers:
            self.__observers.append(observer)

    def _Remove_observer(self, observer) -> None:
        """Remove the observer."""

        if observer in self.observers:
            self.__observers.remove(observer)

    def _Notify(self, event: str) -> None:
        """Notifies the observers."""

        [observer._Update(self, event) for observer in self.observers]

class _IObserver(ABC):
    """The observer interface"""
    @abstractmethod
    def _Update(self, observable: Observable, event: str) -> None:
        """Receive an update/event from an observable object (observer pattern)."""
        pass