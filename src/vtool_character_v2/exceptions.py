"""
Módulo de excepciones personalizadas para vtool_character_v2.
"""


class VToolCharacterV2Error(Exception):
    """
    Excepción base de toda la librería.
    Cualquier error lanzado por vtool_character_v2 hereda de esta clase.
    """
    pass


class LoadCancelledError(VToolCharacterV2Error):
    """
    La carga de un personaje fue cancelada externamente
    (nueva solicitud de carga, refresh de página, etc.).
    Interna — no se propaga al usuario final.
    """
    pass
