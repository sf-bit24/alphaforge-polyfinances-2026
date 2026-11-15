## Tableaux par fenêtre (poche B, CAD 1977+, panier s = 0,5, retraits 4 %)

### p35_B_cad/20261114T235443Z_non_overlapping_h15.json  (choix robuste du run : `bnc_pondere_usdfi`)

| fenêtre | ORACLE, poids (> 3 %) | ORACLE richesse réelle finale | ORACLE maxDD | meilleure ex-ante (a posteriori) | sa richesse réelle | risk_parity_36m richesse réelle | risk_parity_36m maxDD | risk_parity_36m réel ann. (panier) | bnc_pondere richesse | bnc_equilibre richesse | e40_u50 richesse |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1977-01..1991-12 | US_MKT 0.40, CA_TBILL 0.35, GOLD 0.15, US_IND_NODUR 0.10 | 1.722 | 0.150 | momentum_top3 | 2.517 | 1.075 | 0.109 | 0.0508 | 1.254 | 1.417 | 1.195 |
| 1992-01..2006-12 | CA_EQ 0.55, CA_GOV_10Y 0.35, US_IND_NODUR 0.10 | 2.185 | 0.150 | bnc_actions | 2.536 | 1.505 | 0.055 | 0.0623 | 1.949 | 2.118 | 1.731 |
| 2007-01..2021-12 | US_MKT 0.52, GOLD 0.15, UST_5Y 0.12, CA_GOV_10Y 0.11, US_IND_HLTH 0.10 | 1.574 | 0.150 | bnc_actions | 1.548 | 1.049 | 0.051 | 0.0435 | 1.038 | 1.188 | 0.948 |

### p35_B_cad/20261114T235420Z_non_overlapping_h20.json  (choix robuste du run : `bnc_pondere`)

| fenêtre | ORACLE, poids (> 3 %) | ORACLE richesse réelle finale | ORACLE maxDD | meilleure ex-ante (a posteriori) | sa richesse réelle | risk_parity_36m richesse réelle | risk_parity_36m maxDD | risk_parity_36m réel ann. (panier) | bnc_pondere richesse | bnc_equilibre richesse | e40_u50 richesse |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1977-01..1996-12 | US_MKT 0.90, US_IND_NODUR 0.10 | 4.041 | 0.304 | momentum_top3 | 3.789 | 1.270 | 0.109 | 0.0559 | 1.713 | 2.058 | 1.537 |
| 1997-01..2016-12 | CA_EQ 0.49, GOLD 0.15, CA_GOV_10Y 0.14, UST_5Y 0.12, US_IND_HLTH 0.10 | 1.710 | 0.150 | momentum_top3 | 2.113 | 1.376 | 0.045 | 0.0512 | 1.489 | 1.609 | 1.368 |

## Sélection robuste

**p35_B_cad/20261114T235756Z_rolling_h15.json** — 35 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | risk_parity_36m | 1.601 | 2.258 | 1.040 | 0.858 | 0.109 | 0.000 | 0.000 | True |
| 2 | e40_u50_gold15 | 1.481 | 2.186 | 0.993 | 0.824 | 0.113 | 0.000 | 0.000 | True |
| 3 | e40_u50_gold10 | 1.436 | 2.333 | 0.974 | 0.800 | 0.109 | 0.000 | 0.000 | True |
| 4 | bnc_pondere_usdfi | 1.424 | 2.579 | 0.970 | 0.834 | 0.140 | 0.000 | 0.000 | True |
| 5 | e40_u50_def10_gold10 | 1.410 | 2.474 | 0.964 | 0.821 | 0.110 | 0.000 | 0.000 | True |
| 6 | e40_u50_def10 | 1.305 | 2.727 | 0.922 | 0.775 | 0.125 | 0.000 | 0.000 | True |
| 7 | e40_u50 | 1.301 | 2.533 | 0.921 | 0.752 | 0.123 | 0.000 | 0.000 | True |
| 8 | e40_u50_cash10 | 1.174 | 2.457 | 0.869 | 0.721 | 0.122 | 0.000 | 0.000 | True |
| 9 | e40_u25 | 1.166 | 2.762 | 0.867 | 0.644 | 0.123 | 0.000 | 0.000 | True |
| 10 | glide_e50_to_e30 | 1.166 | 2.809 | 0.866 | 0.697 | 0.151 | 0.029 | 0.000 | True |

**p35_B_cad/20261114T235443Z_non_overlapping_h15.json** — 3 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | bnc_pondere_usdfi | 1.730 | 2.167 | 1.092 | 1.048 | 0.137 | 0.000 | 0.000 | True |
| 2 | bnc_pondere | 1.702 | 2.135 | 1.081 | 1.038 | 0.134 | 0.000 | 0.000 | True |
| 3 | e40_u50_def10_gold10 | 1.701 | 2.348 | 1.080 | 1.015 | 0.110 | 0.000 | 0.000 | True |
| 4 | e40_u50_gold15 | 1.684 | 2.088 | 1.074 | 1.033 | 0.113 | 0.000 | 0.000 | True |
| 5 | risk_parity_36m | 1.635 | 1.687 | 1.054 | 1.049 | 0.109 | 0.000 | 0.000 | True |
| 6 | e40_u75 | 1.627 | 2.084 | 1.051 | 1.005 | 0.128 | 0.000 | 0.000 | True |
| 7 | e40_u50_gold10 | 1.625 | 2.072 | 1.050 | 1.005 | 0.109 | 0.000 | 0.000 | True |
| 8 | e40_u50_def10 | 1.577 | 2.283 | 1.031 | 0.960 | 0.125 | 0.000 | 0.000 | True |
| 9 | e40_u50 | 1.493 | 1.986 | 0.997 | 0.948 | 0.123 | 0.000 | 0.000 | True |
| 10 | e30_u50_gold10 | 1.414 | 1.879 | 0.966 | 0.919 | 0.091 | 0.000 | 0.000 | True |

**p35_B_cad/20261114T235713Z_rolling_h20.json** — 30 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | e40_u0 | 4.718 | 8.616 | 1.144 | 0.676 | 0.134 | 0.000 | 0.000 | True |
| 2 | risk_parity_36m | 4.544 | 7.142 | 1.109 | 0.986 | 0.109 | 0.000 | 0.000 | True |
| 3 | e40_u50_gold15 | 4.232 | 6.648 | 1.046 | 0.990 | 0.113 | 0.000 | 0.000 | True |
| 4 | e40_u25 | 4.126 | 8.684 | 1.025 | 0.773 | 0.123 | 0.000 | 0.000 | True |
| 5 | e40_u50_def10_gold10 | 4.091 | 7.608 | 1.018 | 0.931 | 0.110 | 0.000 | 0.000 | True |
| 6 | e40_u50_gold10 | 3.916 | 7.194 | 0.983 | 0.941 | 0.109 | 0.000 | 0.000 | True |
| 7 | bnc_pondere_usdfi | 3.788 | 8.459 | 0.958 | 0.854 | 0.140 | 0.000 | 0.000 | True |
| 8 | e40_u50_def10 | 3.695 | 8.466 | 0.939 | 0.831 | 0.125 | 0.000 | 0.000 | True |
| 9 | e30_u50_gold10 | 3.454 | 6.890 | 0.891 | 0.799 | 0.099 | 0.000 | 0.000 | True |
| 10 | e40_u50 | 3.416 | 8.158 | 0.883 | 0.844 | 0.123 | 0.000 | 0.000 | True |

**p35_B_cad/20261114T235420Z_non_overlapping_h20.json** — 2 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | bnc_pondere | 6.555 | 7.003 | 1.511 | 1.489 | 0.134 | 0.000 | 0.000 | True |
| 2 | e40_u50_def10 | 6.271 | 6.772 | 1.454 | 1.429 | 0.125 | 0.000 | 0.000 | True |
| 3 | e40_u25 | 6.223 | 6.317 | 1.445 | 1.440 | 0.121 | 0.000 | 0.000 | True |
| 4 | bnc_pondere_usdfi | 6.209 | 6.822 | 1.442 | 1.411 | 0.137 | 0.000 | 0.000 | True |
| 5 | e40_u50_def10_gold10 | 6.071 | 6.606 | 1.414 | 1.387 | 0.110 | 0.000 | 0.000 | True |
| 6 | glide_e50_to_e30 | 5.961 | 6.461 | 1.392 | 1.367 | 0.122 | 0.000 | 0.000 | True |
| 7 | e40_u50 | 5.925 | 6.262 | 1.385 | 1.368 | 0.123 | 0.000 | 0.000 | True |
| 8 | e40_u0 | 5.804 | 6.268 | 1.361 | 1.337 | 0.134 | 0.000 | 0.000 | True |
| 9 | e40_u50_gold10 | 5.768 | 6.152 | 1.354 | 1.334 | 0.109 | 0.000 | 0.000 | True |
| 10 | bnc_conservateur | 5.767 | 5.850 | 1.353 | 1.349 | 0.110 | 0.000 | 0.000 | True |

**p35_B_cad_s03/20261114T235429Z_rolling_h15.json** — 35 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | risk_parity_36m | 1.671 | 2.253 | 1.068 | 0.948 | 0.109 | 0.000 | 0.000 | True |
| 2 | e40_u50_gold15 | 1.522 | 2.271 | 1.009 | 0.911 | 0.113 | 0.000 | 0.000 | True |
| 3 | e40_u50_def10_gold10 | 1.458 | 2.485 | 0.983 | 0.908 | 0.110 | 0.000 | 0.000 | True |
| 4 | e40_u50_gold10 | 1.448 | 2.382 | 0.979 | 0.885 | 0.109 | 0.000 | 0.000 | True |
| 5 | bnc_pondere_usdfi | 1.355 | 2.571 | 0.942 | 0.845 | 0.140 | 0.000 | 0.000 | True |
| 6 | e40_u50 | 1.330 | 2.581 | 0.932 | 0.833 | 0.123 | 0.000 | 0.000 | True |
| 7 | e40_u50_def10 | 1.314 | 2.748 | 0.925 | 0.858 | 0.125 | 0.000 | 0.000 | True |
| 8 | glide_e50_to_e30 | 1.252 | 2.879 | 0.901 | 0.774 | 0.151 | 0.029 | 0.000 | True |
| 9 | e40_u25 | 1.228 | 2.591 | 0.891 | 0.716 | 0.123 | 0.000 | 0.000 | True |
| 10 | e40_u50_cash10 | 1.201 | 2.406 | 0.880 | 0.800 | 0.122 | 0.000 | 0.000 | True |

**p35_B_cad_s07/20261114T235427Z_rolling_h15.json** — 35 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | risk_parity_36m | 1.548 | 2.319 | 1.019 | 0.781 | 0.109 | 0.000 | 0.000 | True |
| 2 | e40_u50_gold15 | 1.430 | 2.191 | 0.972 | 0.749 | 0.113 | 0.000 | 0.000 | True |
| 3 | bnc_pondere_usdfi | 1.418 | 2.699 | 0.967 | 0.758 | 0.140 | 0.000 | 0.000 | True |
| 4 | e40_u50_gold10 | 1.386 | 2.330 | 0.954 | 0.727 | 0.109 | 0.000 | 0.000 | True |
| 5 | e40_u50_def10_gold10 | 1.361 | 2.527 | 0.944 | 0.747 | 0.110 | 0.000 | 0.000 | True |
| 6 | e40_u50 | 1.293 | 2.497 | 0.917 | 0.682 | 0.123 | 0.000 | 0.000 | True |
| 7 | e40_u50_def10 | 1.267 | 2.695 | 0.907 | 0.704 | 0.125 | 0.000 | 0.000 | True |
| 8 | e40_u50_cash10 | 1.209 | 2.389 | 0.884 | 0.653 | 0.122 | 0.000 | 0.000 | True |
| 9 | glide_e50_to_e30 | 1.182 | 2.721 | 0.873 | 0.632 | 0.151 | 0.029 | 0.000 | True |
| 10 | e40_u75 | 1.167 | 2.189 | 0.867 | 0.782 | 0.128 | 0.000 | 0.000 | True |

**p35_B_cad_h10/20261114T235436Z_rolling_h10.json** — 40 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | e40_u50_gold15 | 0.623 | 0.960 | 0.974 | 0.770 | 0.113 | 0.000 | 0.000 | True |
| 2 | e40_u50_gold10 | 0.615 | 0.987 | 0.969 | 0.783 | 0.109 | 0.000 | 0.000 | True |
| 3 | risk_parity_36m | 0.598 | 0.963 | 0.959 | 0.825 | 0.109 | 0.000 | 0.000 | True |
| 4 | e40_u50_def10_gold10 | 0.572 | 1.069 | 0.943 | 0.778 | 0.110 | 0.000 | 0.000 | True |
| 5 | e40_u50_def10 | 0.553 | 0.977 | 0.932 | 0.738 | 0.125 | 0.000 | 0.000 | True |
| 6 | e40_u50 | 0.511 | 0.939 | 0.907 | 0.785 | 0.123 | 0.000 | 0.000 | True |
| 7 | e40_u50_cash10 | 0.480 | 0.908 | 0.888 | 0.790 | 0.122 | 0.000 | 0.000 | True |
| 8 | bnc_pondere_usdfi | 0.473 | 0.994 | 0.884 | 0.816 | 0.140 | 0.000 | 0.000 | True |
| 9 | e30_u50 | 0.467 | 0.823 | 0.880 | 0.697 | 0.114 | 0.000 | 0.000 | True |
| 10 | bnc_conservateur | 0.467 | 1.025 | 0.880 | 0.654 | 0.152 | 0.100 | 0.000 | True |

**p35_B_usd1926/20261114T235835Z_rolling_h15.json** — 86 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | bncus_prudent | -0.111 | 0.766 | 0.356 | 0.267 | 0.153 | 0.058 | 0.163 | True |
| 2 | e20_5y | -0.111 | 0.766 | 0.356 | 0.267 | 0.153 | 0.058 | 0.163 | True |
| 3 | risk_parity_36m | -0.218 | 0.871 | 0.313 | 0.187 | 0.147 | 0.000 | 0.209 | True |
| 4 | cash_100 | -0.625 | 0.143 | 0.150 | 0.065 | 0.001 | 0.000 | 0.407 | True |
| 5 | bncus_croissance | 0.527 | 2.596 | 0.611 | 0.251 | 0.722 | 1.000 | 0.035 | False |
| 6 | e60_10y | 0.460 | 2.286 | 0.584 | 0.234 | 0.587 | 0.826 | 0.058 | False |
| 7 | bncus_equilibre | 0.444 | 1.980 | 0.577 | 0.274 | 0.570 | 0.826 | 0.035 | False |
| 8 | e60_5y | 0.444 | 1.980 | 0.577 | 0.274 | 0.570 | 0.826 | 0.035 | False |
| 9 | e50_5y | 0.390 | 1.641 | 0.556 | 0.283 | 0.478 | 0.570 | 0.047 | False |
| 10 | e50_10y | 0.353 | 1.977 | 0.541 | 0.232 | 0.502 | 0.570 | 0.070 | False |

**p35_B_usd1926/20261114T235442Z_non_overlapping_h15.json** — 6 fenêtres

| rang | stratégie | p10 score | médiane score | richesse réelle finale p10 | pire richesse réelle | pire maxDD | taux de violation | P(sous la cible) | éligible |
|---|---|---|---|---|---|---|---|---|---|
| 1 | risk_parity_36m | 0.032 | 0.905 | 0.413 | 0.216 | 0.123 | 0.000 | 0.167 | True |
| 2 | cash_100 | -0.481 | 0.221 | 0.208 | 0.079 | 0.001 | 0.000 | 0.333 | True |
| 3 | e60_10y | 1.054 | 1.889 | 0.821 | 0.688 | 0.587 | 0.833 | 0.000 | False |
| 4 | bncus_croissance | 1.000 | 2.137 | 0.800 | 0.731 | 0.722 | 1.000 | 0.000 | False |
| 5 | bncus_actions | 0.992 | 2.081 | 0.797 | 0.716 | 0.837 | 1.000 | 0.000 | False |
| 6 | bncus_equilibre | 0.941 | 1.871 | 0.776 | 0.720 | 0.570 | 0.833 | 0.000 | False |
| 7 | e60_5y | 0.941 | 1.871 | 0.776 | 0.720 | 0.570 | 0.833 | 0.000 | False |
| 8 | e50_10y | 0.905 | 1.497 | 0.762 | 0.665 | 0.502 | 0.667 | 0.000 | False |
| 9 | e50_5y | 0.889 | 1.367 | 0.756 | 0.705 | 0.478 | 0.667 | 0.000 | False |
| 10 | bncus_pondere | 0.859 | 1.143 | 0.744 | 0.696 | 0.428 | 0.500 | 0.000 | False |

## Walk-forward
- `p35_B_cad/20261114T235756Z_rolling_h15.json` : {'n_oos_windows': 18, 'mean_oos_score': 1.3277191863964493, 'p10_oos_score': 0.541785239132513, 'oos_shortfall_prob': 0.0, 'mean_oracle_gap': 2.5001150698416454} ; choix : {'e40_u100': 10, 'glide_e50_to_e30': 3, 'e40_u50_def10': 2, 'bnc_pondere_usdfi': 2, 'e40_u50_def10_gold10': 1}
- `p35_B_cad/20261114T235713Z_rolling_h20.json` : {'n_oos_windows': 8, 'mean_oos_score': 4.2027799438185385, 'p10_oos_score': 3.3472178836087907, 'oos_shortfall_prob': 0.0, 'mean_oracle_gap': 3.19706134584405} ; choix : {'bnc_pondere': 6, 'bnc_pondere_usdfi': 2}
- `p35_B_cad_h10/20261114T235436Z_rolling_h10.json` : {'n_oos_windows': 28, 'mean_oos_score': 0.7612411312499371, 'p10_oos_score': 0.17500112762463094, 'oos_shortfall_prob': 0.07142857142857142, 'mean_oracle_gap': None} ; choix : {'glide_e50_to_e30': 10, 'e40_u0': 8, 'e40_u50_def10_gold10': 7, 'bnc_pondere_usdfi': 1, 'bnc_pondere': 1, 'e40_u25': 1}
- `p35_B_usd1926/20261114T235835Z_rolling_h15.json` : {'n_oos_windows': 69, 'mean_oos_score': 1.5146900261501557, 'p10_oos_score': -0.10147989370050121, 'oos_shortfall_prob': 0.11594202898550725, 'mean_oracle_gap': 2.1645277337734314} ; choix : {'risk_parity_36m': 47, 'e30_10y': 12, 'e20_10y': 10}

## Plages des poids ORACLE (p10 / médiane / p90)
- oracle_ranges_B15 : CA_EQ 0.00/0.00/0.42; US_MKT 0.00/0.43/0.59; US_IND_NODUR 0.00/0.04/0.10; US_IND_HLTH 0.00/0.00/0.10; CA_GOV_10Y 0.00/0.43/0.47; UST_5Y 0.00/0.00/0.00; CA_TBILL 0.00/0.00/0.00; UST_TBILL 0.00/0.00/0.00; GOLD 0.00/0.00/0.15
- oracle_ranges_B20 : CA_EQ 0.00/0.17/0.42; US_MKT 0.00/0.33/0.90; US_IND_NODUR 0.00/0.01/0.10; US_IND_HLTH 0.00/0.09/0.10; CA_GOV_10Y 0.00/0.33/0.48; UST_5Y 0.00/0.00/0.09; CA_TBILL 0.00/0.00/0.00; UST_TBILL 0.00/0.00/0.00; GOLD 0.00/0.00/0.15
- oracle_ranges_A : UST_TBILL 0.00/0.61/1.00; UST_2Y 0.00/0.00/0.44; UST_5Y 0.00/0.00/0.44; CA_TBILL 0.00/0.00/0.62; CA_GOV_10Y 0.00/0.00/0.55

## Tickers réels `p35_B_tickers/20261114T235401Z_non_overlapping_h4.9167.json`
| stratégie | nominal CAD | réel CAD (IPC CA) | nominal USD | réel USD (CPI US) | réel panier s=0,5 | maxDD CAD | richesse réelle finale (retraits 4 %) |
|---|---|---|---|---|---|---|---|
| e40_u50_gold15 | 0.0898 | 0.0535 | 0.0603 | 0.0186 | 0.0354 | 0.102 | 0.950 |
| e40_u50 | 0.0669 | 0.0313 | 0.0380 | -0.0028 | 0.0136 | 0.120 | 0.845 |
| e40_u50_gold10 | 0.0822 | 0.0461 | 0.0529 | 0.0115 | 0.0282 | 0.108 | 0.914 |
| e40_u50_def10_gold10 | 0.0795 | 0.0435 | 0.0503 | 0.0089 | 0.0256 | 0.096 | 0.903 |
| bnc_prudent | 0.0336 | -0.0009 | 0.0056 | -0.0340 | -0.0180 | 0.131 | 0.710 |
| bnc_conservateur | 0.0483 | 0.0133 | 0.0199 | -0.0202 | -0.0041 | 0.135 | 0.767 |
| bnc_pondere | 0.0702 | 0.0346 | 0.0413 | 0.0003 | 0.0168 | 0.140 | 0.858 |
| bnc_equilibre | 0.0921 | 0.0557 | 0.0626 | 0.0208 | 0.0376 | 0.146 | 0.957 |
| bnc_croissance | 0.1213 | 0.0839 | 0.0909 | 0.0480 | 0.0653 | 0.153 | 1.102 |
| bnc_actions | 0.1503 | 0.1119 | 0.1191 | 0.0751 | 0.0928 | 0.160 | 1.262 |
| bnc_pondere_usdfi | 0.0735 | 0.0377 | 0.0444 | 0.0033 | 0.0199 | 0.134 | 0.873 |
| e40_u0 | 0.0582 | 0.0230 | 0.0296 | -0.0109 | 0.0054 | 0.117 | 0.806 |
| e40_u100 | 0.0754 | 0.0396 | 0.0463 | 0.0051 | 0.0217 | 0.128 | 0.884 |
| e40_u50_cash10 | 0.0711 | 0.0354 | 0.0421 | 0.0011 | 0.0176 | 0.109 | 0.864 |

ORACLE tickers : SPY 0.75, GLD 0.15, JNJ 0.10 ; richesse réelle 1.389 ; maxDD 0.136