# Regione Abruzzo - legislazione regionale (proposta)

## Strumenti MCP

* cerca_leggi_regione_abruzzo(parole, numero, anno_da, anno_a, max_risultati)
  ricerca nell'indice istituzionale Normattiva Regioni, che rimanda ai testi
  della Regione Abruzzo. Gli anni si riferiscono all'anno della legge;
  l'indice puo' riportare lo stato VIGENTE, da verificare con le fonti ufficiali.
  Un risultato vuoto NON dimostra che la legge regionale non esista.
* leggi_legge_regione_abruzzo(codice_redazionale, data_pubblicazione,
  articolo, da_carattere) legge il testo pubblicato. Controlla gli indizi della
  provenienza dall'Abruzzo ed estrae solo l'articolo se identificabile.
  Usa finestre fino a 25.000 caratteri per norme lunghe.

## Limitazione essenziale

Il testo GU NON e' automaticamente il testo vigente o coordinato: la GU
serie Regioni puo' pubblicare le leggi con ritardo rispetto al BURAT.
Il sistema NON accerta automaticamente le successive modifiche,
abrogazioni o la multivigenza. Per pratiche e perizie verificare:

- Regione Abruzzo, testi storici e vigenti:
  https://www.regione.abruzzo.it/leggi-atti-bandi/leggi-e-progetti-di-legge
- Bollettino ufficiale BURAT:
  https://bura.regione.abruzzo.it/
- Raccolta legislativa regionale indicizzata da Normattiva:
  https://www.normattiva.it/legislazioneRegionale/abruzzo

## Esempio di fonte verificata

La legge regionale Abruzzo n. 58 del 20 dicembre 2023 e' disponibile in
GU serie Regioni n. 37 del 21 settembre 2024, codice 24R00001. La lettura
con il tool preesistente leggi_atto_gazzetta e' stata verificata.
La nuova interfaccia e' da collaudare prima dell'uso nel server Render.

## Deploy

Il branch feature/leggi-regionali-abruzzo-20261018 deriva dal branch OAuth
gia' pubblicato su Render. NON fare merge/deploy prima dei test e della
verifica diretta sulla pagina GU. Non cambiare o esporre i segreti OAuth.
