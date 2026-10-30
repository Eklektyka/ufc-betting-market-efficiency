# Origin Coding Rules

## Sources
- **Primary**: Wikidata (P27 country of citizenship, P19 birthplace) — 1,413/1,886 fighters matched (74.9%)
- **Supplementary (Russia only)**: roster.watch full Russia-filtered roster (active + former), manually provided. Covers all fighters ever flagged as Russian on the UFC roster.

## Three-way Russian Federation split

### Ethnic Russian
Fighters flagged as Russian (🇷🇺) on roster.watch whose birthplace (from Wikidata or name/context) is NOT in the North Caucasus region. Includes fighters with dual flags where 🇷🇺 is present and the fighter is ethnically Russian by name/origin.

### Caucasus (Dagestani, Chechen, Ingush, Ossetian, other North Caucasus)
Russian-flagged fighters whose birthplace coordinates fall within lat 41-45°N, lon 43-49°E, OR whose birthplace text matches known Caucasus cities/regions. List of markers: dagestan, chechnya, chechen, grozny, makhachkala, ingush, kabardino, karachay, ossetia, nalchik, khasavyurt, buynaksk, derbent, nazran, kizlyar, kaspiysk, kizilyurt, sildi, sunzha, teletl, achkhoy, aymaki, dylym, madzhalis, mekegi, kasumkent, kamysh-kutan, goksuv, batayurt, gvardeyskoe, babugent, vladikavkaz.

### Central Asian
Fighters with Wikidata nationality in: Kazakhstan, Kyrgyzstan, Uzbekistan, Tajikistan, Turkmenistan.

## Control groups (Wikidata only)
- USA: country = United States
- Brazil: country = Brazil
- UK: country = United Kingdom
- Canada: country = Canada
- Australia: country = Australia
- Other: all remaining matched fighters

## Ambiguous cases

| Fighter | Decision | Alternative | Reason |
|---|---|---|---|
| Khamzat Chimaev | Caucasus | Ethnic Russian or Swedish | Born Chechnya (🇦🇪🇷🇺🇸🇪), fights out of Sweden. Coded Caucasus by birthplace. |
| Arman Tsarukyan | Caucasus/Georgia | Ethnic Russian | Armenian (🇦🇲🇷🇺), born in Georgia. Coded via Wikidata as Armenian, falls into Caucasus/Georgia group. |
| Nikita Krylov | Ethnic Russian | Ukrainian | Dual 🇷🇺🇺🇦, born Ukraine. Coded as Russian per roster.watch flag. |
| Valter Walker | Ethnic Russian | Brazilian | Dual 🇧🇷🇷🇺, trains in Russia, identifies with Russia. Coded ethnic Russian per user instruction. |
| Dennis Siver | Ethnic Russian | German | Dual 🇩🇪🇷🇺, born Russia, fought under German flag. Coded ethnic Russian for Russia analysis; German for nation-map. |
| Nassourdine Imavov | Other (France) | Ethnic Russian | Dual 🇫🇷🇷🇺, fights under French flag. Coded France. |
| Artem Lobov | Other (Ireland) | Ethnic Russian | Dual 🇮🇪🇷🇺, fought under Irish flag. Coded Ireland. |
| Abus Magomedov | Caucasus | German | Dual 🇩🇪🇷🇺, Dagestan-origin name. Coded Caucasus by name/origin. |
| Muhammad Mokaev | Other (UK) | Caucasus | Dual 🇬🇧🇷🇺, Dagestan-born, fights under UK flag. Coded UK. |
| Damir Ismagulov | Ethnic Russian | Central Asian | Dual 🇰🇿🇷🇺, born Orenburg (Russia). Coded ethnic Russian by birthplace. |
| Yana Santos | Ethnic Russian | Brazilian | 🇷🇺 flag, Russian-born, fights out of Brazil. Coded ethnic Russian. |
| Ismail Naurdiev | Other (Austria) | Ethnic Russian | Triple 🇦🇹🇲🇦🇷🇺, fights under Austrian flag. Coded Austria/Other. |

## Coverage bias note
Wikidata systematically over-covers successful/notable fighters. The roster.watch supplement corrects this for Russia only. Control groups (USA, Brazil, etc.) remain on Wikidata coding and may have similar positive-selection bias. The coverage diagnostic table (Step 1c) quantifies this.
