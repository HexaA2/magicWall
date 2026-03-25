from pathlib import Path
import math

import pandas as pd
from scipy import stats


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOWNSTATE_COUNTIES = {
	"Bronx County",
	"Kings County",
	"New York County",
	"Queens County",
	"Richmond County",
	"Nassau County",
	"Suffolk County",
	"Westchester County",
	"Rockland County",
	"Putnam County",
	"Orange County",
	"Dutchess County",
	"Ulster County",
	"Sullivan County",
}


def load_ny_counties_dataframe() -> pd.DataFrame:
	"""Return one row per New York county with 2020 and 2024 columns side by side."""
	csv_by_year = {
		2020: DATA_DIR / "2020_US_County_Level_Presidential_Results.csv",
		2024: DATA_DIR / "2024_US_County_Level_Presidential_Results.csv",
	}
	key_columns = ["state_name", "county_fips", "county_name"]

	ny_by_year = {}
	for year, csv_path in csv_by_year.items():
		df = pd.read_csv(csv_path, dtype={"county_fips": "string"})
		ny_df = df[df["state_name"] == "New York"].copy()
		rename_map = {
			column: f"{column}_{year}"
			for column in ny_df.columns
			if column not in key_columns
		}
		ny_by_year[year] = ny_df.rename(columns=rename_map)

	combined_df = ny_by_year[2020].merge(
		ny_by_year[2024],
		on=key_columns,
		how="outer",
		validate="one_to_one",
	)

	return combined_df.sort_values("county_fips").reset_index(drop=True)


def two_proportion_z_test(success_a: int, n_a: int, success_b: int, n_b: int) -> dict:
	"""Run a two-proportion z-test and return summary stats."""
	if n_a == 0 or n_b == 0:
		return {
			"p_2020": math.nan,
			"p_2024": math.nan,
			"z_score": math.nan,
			"p_value_two_tailed": math.nan,
			"p_value_one_tailed": math.nan,
		}

	p_a = success_a / n_a
	p_b = success_b / n_b
	pooled_p = (success_a + success_b) / (n_a + n_b)
	standard_error = math.sqrt(pooled_p * (1 - pooled_p) * ((1 / n_a) + (1 / n_b)))
	if standard_error == 0:
		return {
			"p_2020": p_a,
			"p_2024": p_b,
			"z_score": math.nan,
			"p_value_two_tailed": math.nan,
			"p_value_one_tailed": math.nan,
		}

	z_score = (p_a - p_b) / standard_error
	# Phi(z) from erf for the standard normal CDF.
	cdf_z = 0.5 * (1 + math.erf(z_score / math.sqrt(2)))
	p_value_two_tailed = 2 * min(cdf_z, 1 - cdf_z)
	# One-tailed for H1: p_2020 > p_2024 (matches z = p_2020 - p_2024).
	p_value_one_tailed = 1 - cdf_z

	return {
		"p_2020": p_a,
		"p_2024": p_b,
		"z_score": z_score,
		"p_value_two_tailed": p_value_two_tailed,
		"p_value_one_tailed": p_value_one_tailed,
	}


def welch_t_test(group_a: pd.Series, group_b: pd.Series) -> dict:
	"""Compare means of two groups with Welch's t-test (unequal variances)."""
	clean_a = group_a.dropna()
	clean_b = group_b.dropna()

	if len(clean_a) < 2 or len(clean_b) < 2:
		return {
			"n_upstate": len(clean_a),
			"n_downstate": len(clean_b),
			"mean_upstate": clean_a.mean() if len(clean_a) else math.nan,
			"mean_downstate": clean_b.mean() if len(clean_b) else math.nan,
			"t_stat": math.nan,
			"p_value_two_tailed": math.nan,
		}

	t_stat, p_value = stats.ttest_ind(clean_a, clean_b, equal_var=False)

	return {
		"n_upstate": len(clean_a),
		"n_downstate": len(clean_b),
		"mean_upstate": clean_a.mean(),
		"mean_downstate": clean_b.mean(),
		"t_stat": t_stat,
		"p_value_two_tailed": p_value,
	}


def add_county_level_metrics(df: pd.DataFrame) -> pd.DataFrame:
	"""Append county-level totals, percentages, and z-test outputs to each row."""
	enriched_df = df.copy()
	alpha = 0.05

	enriched_df["county_dem_total_2020"] = enriched_df["votes_dem_2020"]
	enriched_df["county_dem_total_2024"] = enriched_df["votes_dem_2024"]
	enriched_df["county_total_votes_2020"] = enriched_df["total_votes_2020"]
	enriched_df["county_total_votes_2024"] = enriched_df["total_votes_2024"]
	enriched_df["county_region"] = enriched_df["county_name"].apply(
		lambda county: "downstate" if county in DOWNSTATE_COUNTIES else "upstate"
	)

	enriched_df["county_dem_percent_2020"] = (
		enriched_df["county_dem_total_2020"] / enriched_df["county_total_votes_2020"]
	) * 100
	enriched_df["county_dem_percent_2024"] = (
		enriched_df["county_dem_total_2024"] / enriched_df["county_total_votes_2024"]
	) * 100

	z_results = enriched_df.apply(
		lambda row: two_proportion_z_test(
			success_a=int(row["county_dem_total_2020"]),
			n_a=int(row["county_total_votes_2020"]),
			success_b=int(row["county_dem_total_2024"]),
			n_b=int(row["county_total_votes_2024"]),
		),
		axis=1,
		result_type="expand",
	)

	enriched_df["county_dem_share_2020"] = z_results["p_2020"]
	enriched_df["county_dem_share_2024"] = z_results["p_2024"]
	enriched_df["county_change_dem_percent"] = (
		enriched_df["county_dem_percent_2024"] - enriched_df["county_dem_percent_2020"]
	)
	enriched_df["county_z_score"] = z_results["z_score"]
	enriched_df["county_p_value_two_tailed"] = z_results["p_value_two_tailed"]
	enriched_df["county_statistically_significant"] = enriched_df[
		"county_p_value_two_tailed"
	].apply(lambda p: "yes" if pd.notna(p) and p < alpha else "no")

	return enriched_df


if __name__ == "__main__":
	ny_counties_df = load_ny_counties_dataframe()
	ny_counties_df = add_county_level_metrics(ny_counties_df)
	output_csv_path = BASE_DIR / "NY_counties_2020_2024_enriched.csv"
	ny_counties_df.to_csv(output_csv_path, index=False)

	total_dem_votes_2020 = int(ny_counties_df["votes_dem_2020"].sum())
	total_dem_votes_2024 = int(ny_counties_df["votes_dem_2024"].sum())

	total_votes_2020 = int(ny_counties_df["total_votes_2020"].sum())
	total_votes_2024 = int(ny_counties_df["total_votes_2024"].sum())

	dem_percent_2020 = (total_dem_votes_2020 / total_votes_2020) * 100 if total_votes_2020 else 0.0
	dem_percent_2024 = (total_dem_votes_2024 / total_votes_2024) * 100 if total_votes_2024 else 0.0
	z_test_result = two_proportion_z_test(
		success_a=total_dem_votes_2020,
		n_a=total_votes_2020,
		success_b=total_dem_votes_2024,
		n_b=total_votes_2024,
	)
	welch_result = welch_t_test(
		ny_counties_df.loc[ny_counties_df["county_region"] == "upstate", "county_change_dem_percent"],
		ny_counties_df.loc[ny_counties_df["county_region"] == "downstate", "county_change_dem_percent"],
	)

	print(f"Exported county dataframe to: {output_csv_path}")
	print(f"Rows: {len(ny_counties_df)}")
	print(f"Dem total 2020: {total_dem_votes_2020}")
	print(f"Dem total 2024: {total_dem_votes_2024}")
	print(f"Total 2020: {total_votes_2020}")
	print(f"Total 2024: {total_votes_2024}")
	print(f"Dem % 2020: {dem_percent_2020:.2f}%")
	print(f"Dem % 2024: {dem_percent_2024:.2f}%")
	print(f"Two-proportion z-score: {z_test_result['z_score']:.4f}")
	print(f"Two-proportion p-value (two-tailed): {z_test_result['p_value_two_tailed']:.3f}")
	print(
		"Welch t-test (county_change_dem_percent, upstate vs downstate): "
		f"t={welch_result['t_stat']:.4f}, p={welch_result['p_value_two_tailed']:.3f}"
	)
	print(
		f"Upstate n={welch_result['n_upstate']}, mean={welch_result['mean_upstate']:.4f}; "
		f"Downstate n={welch_result['n_downstate']}, mean={welch_result['mean_downstate']:.4f}"
	)

	county_results_table = ny_counties_df[
		[
			"county_name",
			"county_region",
			"county_change_dem_percent",
			"county_z_score",
			"county_p_value_two_tailed",
			"county_statistically_significant",
		]
	].copy()
	county_results_table["county_p_value_two_tailed"] = county_results_table[
		"county_p_value_two_tailed"
	].map(lambda x: f"{x:.3f}" if pd.notna(x) else "nan")
	significant_count = (ny_counties_df["county_statistically_significant"] == "yes").sum()
	print(f"Statistically significant counties: {significant_count}")
	print("\nCounty-level table:")
	print(county_results_table.to_string(index=False))

    