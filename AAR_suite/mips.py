from tsuklid import arvuta_tsuklite_pikendus


def arvuta_protsessori_labilaskevoime(
    taktsagedus: float,
    vahemalu_edukus: float,
    andmete_edukus: float,
    malu_vajajad: float,
    miss_penalty: int,
    cpi_baas: float = 1.0,
) -> float:
    tsuklite_pikendus = arvuta_tsuklite_pikendus(
        vahemalu_edukus=vahemalu_edukus,
        andmete_edukus=andmete_edukus,
        malu_vajajad=malu_vajajad,
        miss_penalty=miss_penalty,
    )
    cpi_uus = cpi_baas + tsuklite_pikendus

    # Töösagedus Hertzides: GHz * 10^9
    taktsagedus *= 1_000_000_000

    # Käskude läbilaskevõime (IPS) = f / CPI_uus
    ips = taktsagedus / cpi_uus

    # MIPS (Miljonit tehet sekundis) = IPS / 10^6
    mips = ips / 1_000_000

    return mips


def _sisendid_kehtivad(
    taktsagedus: float,
    vahemalu_edukus: float,
    andmete_edukus: float,
    malu_vajajad: float,
    miss_penalty: int,
) -> bool:
    if taktsagedus <= 0:
        return False
    if not (0.0 <= vahemalu_edukus <= 1.0):
        return False
    if not (0.0 <= andmete_edukus <= 1.0):
        return False
    if not (0.0 <= malu_vajajad <= 1.0):
        return False
    if miss_penalty < 0:
        return False
    return True


def mips() -> None:
    try:
        taktsagedus: float = float(input("mis on prose taktsagedus (GHz): "))
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
        taktsagedus, vahemalu_edukus, andmete_edukus, malu_vajajad, miss_penalty
    ):
        print("Vigased sisendid.")
        return

    vastus = arvuta_protsessori_labilaskevoime(
        taktsagedus=taktsagedus,
        vahemalu_edukus=vahemalu_edukus,
        andmete_edukus=andmete_edukus,
        malu_vajajad=malu_vajajad,
        miss_penalty=miss_penalty,
    )

    print(f"Protsessori läbilaskevõime on: {vastus:.0f} MIPS")


if __name__ == "__main__":
    mips()
