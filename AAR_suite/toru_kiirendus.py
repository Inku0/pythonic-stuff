from tsuklid import arvuta_tsuklite_pikendus


def calculate_speedup(
    vahemalu_edukus: float,
    andmete_edukus: float,
    malu_vajajad: float,
    miss_penalty: int,
    pipeline_stages: int = 5,
    cpi_baas: float = 1.0,
) -> float:
    """
    Arvutab torustatud protsessori kiirenduse järjestikulise protsessori suhtes.
    Speedup = CPI_sequential / CPI_pipelined
    """
    tsuklite_pikendus = arvuta_tsuklite_pikendus(
        vahemalu_edukus=vahemalu_edukus,
        andmete_edukus=andmete_edukus,
        malu_vajajad=malu_vajajad,
        miss_penalty=miss_penalty,
    )

    cpi_pipelined = cpi_baas + tsuklite_pikendus
    cpi_sequential = float(pipeline_stages) + tsuklite_pikendus

    if cpi_pipelined <= 0.0:
        return float("inf")

    return cpi_sequential / cpi_pipelined


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


def tore_kiirendus() -> None:
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
        vahemalu_edukus,
        andmete_edukus,
        malu_vajajad,
        miss_penalty,
    ):
        print("Vigased sisendid.")
        return

    vastus = calculate_speedup(
        vahemalu_edukus=vahemalu_edukus,
        andmete_edukus=andmete_edukus,
        malu_vajajad=malu_vajajad,
        miss_penalty=miss_penalty,
    )

    print(f"kiirendus on: {vastus:.1f}")


if __name__ == "__main__":
    tore_kiirendus()
