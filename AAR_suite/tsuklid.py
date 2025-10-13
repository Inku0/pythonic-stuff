def arvuta_tsuklite_pikendus(
    vahemalu_edukus: float,
    andmete_edukus: float,
    malu_vajajad: float,
    miss_penalty: int,
) -> float:
    """
    Arvutab keskmise CPI pikenemise (stall-tsüklite summa käsu kohta) vahemälu puudutuste tõttu.

    Parameetrid:
    - vahemalu_edukus: käskude vahemälust leidmise tõenäosus vahemikus [0.0, 1.0]
    - andmete_edukus: andmete vahemälust leidmise tõenäosus vahemikus [0.0, 1.0]
    - malu_vajajad: nende käskude osakaal, mis vajavad mälust andmeid, vahemikus [0.0, 1.0]
    - miss_penalty: vahemälu möödapaneku karistus tsüklites (täisarv, >= 0)

    Tagastab:
    - tsükli pikenemise (float), mida võib käsitleda kui keskmist lisanduvat CPI-d

    Märkused:
    - Mudel on lihtsustatud: karistus on lineaarne miss-määrade ja osakaalude suhtes.
    """
    # 1. Käskude vahemälu miss rate
    miss_kask = 1.0 - vahemalu_edukus

    # 2. Andmete vahemälu miss rate
    miss_andmed = 1.0 - andmete_edukus

    # 3. Käskude vahemälu karistus per käsu
    karistus_kask = miss_kask * miss_penalty

    # 4. Andmete vahemälu karistus (ainult mälu vajajatele)
    karistus_andmed = malu_vajajad * miss_andmed * miss_penalty

    # 5. Keskmine CPI pikenemine on karistuste summa
    tsuklite_pikendus = karistus_kask + karistus_andmed

    return tsuklite_pikendus


def _sisendid_kehtivad(
    vahemalu_edukus: float,
    andmete_edukus: float,
    malu_vajajad: float,
    miss_penalty: int,
) -> bool:
    if not (0.0 <= vahemalu_edukus <= 1.0):
        return False
    if not (0.0 <= andmete_edukus <= 1.0):
        return False
    if not (0.0 <= malu_vajajad <= 1.0):
        return False
    if miss_penalty < 0:
        return False
    return True


def tsuklid() -> None:
    try:
        vahemalu_edukus: float = float(
            input("käskude vahemälust leidmise tõenäosus (0..1, kümnendmurd): ")
        )
        andmete_edukus: float = float(
            input("andmete vahemälust leidmise tõenäosus (0..1, kümnendmurd): ")
        )
        malu_vajajad: float = float(
            input("nende käskude osakaal, mis vajavad mälust andmeid (0..1): ")
        )
        miss_penalty: int = int(input("miss penalty (täisarv): "))
    except ValueError:
        print("Vigased sisendid.")
        return

    if not _sisendid_kehtivad(
        vahemalu_edukus=vahemalu_edukus,
        andmete_edukus=andmete_edukus,
        malu_vajajad=malu_vajajad,
        miss_penalty=miss_penalty,
    ):
        print("Vigased sisendid.")
        return

    vastus = arvuta_tsuklite_pikendus(
        vahemalu_edukus=vahemalu_edukus,
        andmete_edukus=andmete_edukus,
        malu_vajajad=malu_vajajad,
        miss_penalty=miss_penalty,
    )

    print(f"Keskmine tsuklite pikenemine: {vastus:.2f}")


if __name__ == "__main__":
    tsuklid()
