"""Compile moteur/jbig2/jbig2.c en bibliotheque partagee (philpdf_jbig2.dll sous Windows, .so ailleurs).
Utilise le compilateur que Python sait trouver (Visual Studio sous Windows, gcc/clang ailleurs).
Lancement : python outils_dev/compiler_jbig2.py"""
import os
import sys
import tempfile

ici = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "moteur", "jbig2")
try:
    from setuptools._distutils.ccompiler import new_compiler
    from setuptools._distutils.sysconfig import customize_compiler
except ImportError:                                 # Python ancien
    from distutils.ccompiler import new_compiler
    from distutils.sysconfig import customize_compiler

cc = new_compiler()
customize_compiler(cc)
tmp = tempfile.mkdtemp()
objets = cc.compile([os.path.join(ici, "jbig2.c")], output_dir=tmp,
                    extra_preargs=["/O2"] if sys.platform == "win32" else ["-O2", "-fPIC"])
nom = "philpdf_jbig2"
if sys.platform == "win32":
    sortie = os.path.join(ici, nom + ".dll")
    cc.link_shared_object(objets, sortie)
else:
    sortie = os.path.join(ici, "lib" + nom + (".dylib" if sys.platform == "darwin" else ".so"))
    cc.link_shared_object(objets, sortie)
print("JBIG2 compile :", sortie, os.path.getsize(sortie), "octets")
