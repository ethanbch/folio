"""Builds a folder of fictional files, for screenshots and trying folio without your own files.

Usage: uv run python scripts/demo.py <folder>
Then:  FOLIO_DATA_DIR=<data> with roots = ["<folder>"] in its config.toml.
"""

import os
import sys
import time
import zipfile
from pathlib import Path

FILES = {
    "Maison/Travaux/devis-cuisine-chene-massif.md": "# Devis cuisine\n\nMenuiserie Durand. Plan de travail en chêne massif, 3,2 m. Pose comprise. Total : 8 450 € TTC. Validité : 3 mois.",
    "Maison/Travaux/devis-salle-de-bain.md": "# Devis salle de bain\n\nCarrelage grès cérame 60x60, douche à l'italienne. Total : 6 120 € TTC.",
    "Maison/Assurance/attestation-habitation-2026.txt": "Attestation d'assurance habitation, contrat MRH, période du 1er janvier au 31 décembre 2026.",
    "Travail/Projet Atlas/compte-rendu-reunion-budget-T3.md": "# Réunion budget T3\n\nPrésents : équipe produit, finance. Décisions : le budget marketing baisse de 12 %, le recrutement data est maintenu. Prochaine réunion le 14 octobre.",
    "Travail/Projet Atlas/roadmap-2027.md": "# Feuille de route 2027\n\nTrimestre 1 : refonte de la recherche. Trimestre 2 : application mobile. Trimestre 3 : ouverture de l'API.",
    "Travail/Projet Atlas/kickoff-atlas.md": "# Lancement du projet Atlas\n\nObjectifs, périmètre, planning, gouvernance du projet et comité de pilotage mensuel.",
    "Travail/Clients/Nordis/proposition-commerciale-nordis.md": "# Proposition commerciale\n\nClient : Nordis. Accompagnement sur la gouvernance des données, 40 jours, démarrage en novembre.",
    "Travail/Clients/Nordis/notes-atelier-donnees.txt": "Atelier données avec Nordis : qualité des référentiels clients, doublons, propriétaires des données par domaine.",
    "Cours/Finance/risque-de-marche-var.md": "# Risque de marché\n\nValue at Risk historique, paramétrique et Monte-Carlo. Expected Shortfall. Backtesting de Kupiec.",
    "Cours/Finance/produits-derives-options.md": "# Options\n\nCall, put, parité call-put, modèle de Black-Scholes, grecques : delta, gamma, vega, thêta.",
    "Cours/Econometrie/regression-discontinuite.md": "# Régression sur discontinuité\n\nEffet local d'un traitement au seuil, choix de la fenêtre, tests de manipulation de McCrary.",
    "Cours/Econometrie/donnees-de-panel.md": "# Données de panel\n\nEffets fixes, effets aléatoires, test de Hausman, erreurs groupées.",
    "Voyages/Lisbonne/itineraire-lisbonne.md": "# Lisbonne, 4 jours\n\nAlfama, Belém, tram 28, Sintra le troisième jour. Restaurant réservé le samedi à 20h.",
    "Voyages/Lisbonne/budget-voyage.csv": "poste,montant\nvol,212\nhôtel,384\nrepas,240\ntransports,46\n",
    "Recettes/gratin-dauphinois.txt": "Gratin dauphinois : pommes de terre, crème, lait, ail, muscade. Four à 160 °C pendant 1 h 30.",
    "Recettes/tarte-tatin.txt": "Tarte Tatin : pommes, beurre, sucre, pâte brisée. Caraméliser puis retourner.",
    "Administratif/impots/simulation-impot-2026.csv": "revenu,parts,impot\n42000,1,4120\n",
    "Notes/idees-application.md": "Idées : une recherche de fichiers en langage naturel, locale, qui comprend « le pdf de la semaine dernière ».",
    "Notes/lectures-2026.md": "Lectures : Designing Data-Intensive Applications, AI Engineering, Thinking, Fast and Slow.",
}

DOCX = {
    "Travail/Projet Atlas/presentation-comite-pilotage.docx": "Comité de pilotage Atlas. Avancement : 70 %. Risques : retard du prestataire, budget serré.",
    "Travail/Clients/Nordis/contrat-cadre-nordis.docx": "Contrat cadre de prestations intellectuelles entre Nordis et le prestataire.",
}


def docx(path: Path, text: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", f'<w:document xmlns:w="w"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')


def main() -> None:
    root = Path(sys.argv[1])
    now = time.time()
    for i, (rel, text) in enumerate(list(FILES.items()) + list(DOCX.items())):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".docx"):
            docx(p, text)
        else:
            p.write_text(text)
        t = now - i * 5 * 86400  # spread modification dates over a few months
        os.utime(p, (t, t))
    print(f"{len(FILES) + len(DOCX)} files in {root}")


if __name__ == "__main__":
    main()
