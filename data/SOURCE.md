# Data source

`DATASET.csv` is version 1 of

> Ryckewaert, M. and Feilhes, C. *Spectral dataset of grape berries from
> hyperspectral imaging for maturity monitoring.* Mendeley Data.
> doi:10.17632/gjwx64sgkp

Licensed CC BY. Redistributed here unmodified for reproducibility; cite the
authors above, not this repository.

274 trays of 100 berries, three varieties (SYRAH, MAUZAC, FER), reflectance at
204 bands from 397 to 1003 nm, plus the sugar content in g/L of the juice
pressed from each tray.

To fetch it again:

    curl -sSL "https://data.mendeley.com/public-api/datasets/gjwx64sgkp/files?folder_id=root&version=1"

and follow the download_url in the response.
