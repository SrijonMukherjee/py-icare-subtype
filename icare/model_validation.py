import pathlib
from typing import Union, List, Optional

import numpy as np
import pandas as pd

from icare import check_errors, utils
from icare.absolute_risk_model import AbsoluteRiskModel, format_rates


class ModelValidationResults:
    risk_prediction_interval: str
    reference: dict
    incidence_rates: dict
    dataset_name: str
    model_name: str
    subject_specific_predicted_absolute_risk: pd.Series

    def __init__(self):
        pass

    def set_risk_prediction_interval(self, risk_prediction_interval: str):
        self.risk_prediction_interval = risk_prediction_interval

    def set_dataset_name(self, dataset_name: str):
        self.dataset_name = dataset_name

    def set_model_name(self, model_name: str):
        self.model_name = model_name

    def set_reference_risks(self, reference_absolute_risk: List[float], reference_risk_score: List[float]):
        self.reference = dict()
        self.reference["absolute_risk"] = reference_absolute_risk
        self.reference["risk_score"] = reference_risk_score

    def set_incidence_rates(self, study_ages: List[int], study_incidence: List[float],
                            population_incidence_rates_path: Union[str, pathlib.Path, None] = None) -> None:
        self.incidence_rates = dict()
        self.incidence_rates["study"] = pd.DataFrame({
            "age": study_ages,
            "rate": study_incidence
        })

        if population_incidence_rates_path is not None:
            disease_incidence_rates = format_rates(utils.read_file_to_dataframe(population_incidence_rates_path))

            self.incidence_rates["population"] = pd.DataFrame({
                "age": disease_incidence_rates.index,
                "rate": disease_incidence_rates.values
            })


def get_absolute_risk_parameters(icare_model_parameters: dict) -> dict:
    check_errors.check_icare_model_parameters(icare_model_parameters)
    absolute_risk_parameters = dict()

    absolute_risk_parameter_list = [
        "apply_age_start", "apply_age_interval_length", "age_specific_disease_incidence_rates_path", "formula_path",
        "snp_info_path", "log_relative_risk_path", "reference_dataset_path",
        "model_reference_dataset_weights_variable_name", "age_specific_competing_incidence_rates_path",
        "model_family_history_variable_name", "num_imputations", "covariate_profile_path", "snp_profile_path",
        "return_reference_risks", "seed"
    ]

    icare_model_parameter_list = [
        "apply_age_start", "apply_age_interval_length", "model_disease_incidence_rates_path",
        "model_covariate_formula_path", "model_snp_info_path", "model_log_relative_risk_path",
        "model_reference_dataset_path", "model_reference_dataset_weights_variable_name",
        "model_competing_incidence_rates_path", "model_family_history_variable_name", "num_imputations",
        "apply_covariate_profile_path", "apply_snp_profile_path", "return_reference_risks", "seed"
    ]

    for absolute_risk_param, icare_param in zip(absolute_risk_parameter_list, icare_model_parameter_list):
        default_value = 5 if absolute_risk_param == "num_imputations" else None
        absolute_risk_parameters[absolute_risk_param] = icare_model_parameters[icare_param] \
            if icare_param in icare_model_parameters else default_value

    return absolute_risk_parameters


class ModelValidation:
    study_data: pd.DataFrame
    nested_case_control_study: bool = False
    predicted_risk_variable_name: str
    linear_predictor_variable_name: str

    results: ModelValidationResults

    def __init__(self,
                 study_data_path: Union[str, pathlib.Path],
                 predicted_risk_interval: Union[str, int, List[int]],
                 icare_model_parameters: Optional[dict],
                 predicted_risk_variable_name: Optional[str],
                 linear_predictor_variable_name: Optional[str],
                 number_of_percentiles: int,
                 linear_predictor_cutoffs: Optional[List[float]],
                 dataset_name: str,
                 model_name: str,
                 reference_entry_age: Union[int, List[int], None] = None,
                 reference_exit_age: Union[int, List[int], None] = None,
                 reference_predicted_risks: Optional[List[float]] = None,
                 reference_linear_predictors: Optional[List[float]] = None,
                 seed: Optional[int] = None) -> None:
        # setup
        self.results = ModelValidationResults()
        self.results.set_dataset_name(dataset_name)
        self.results.set_model_name(model_name)
        self._set_study_data(study_data_path, predicted_risk_variable_name, linear_predictor_variable_name)
        self._set_predicted_time_interval(predicted_risk_interval)
        self._calculate_followup_period()

        # calculating predicted risks
        self._calculate_risks(icare_model_parameters, predicted_risk_variable_name, linear_predictor_variable_name,
                              seed)
        self._calculate_reference_risks(icare_model_parameters, reference_entry_age, reference_exit_age,
                                        reference_predicted_risks, reference_linear_predictors, seed)

        # calculating validation metrics
        self._calculate_study_incidence_rates(icare_model_parameters)

    def _set_study_data(self, study_data_path: Union[str, pathlib.Path], predicted_risk_variable_name: Optional[str],
                        linear_predictor_variable_name: Optional[str]) -> None:
        # load study data and set data types
        self.study_data = pd.read_csv(study_data_path)

        mandatory_columns = ["observed_outcome", "study_entry_age", "study_exit_age", "time_of_onset"]
        check_errors.check_data_mandatory_columns(self.study_data, mandatory_columns)
        integer_columns = ["observed_outcome", "study_entry_age", "study_exit_age"]
        self.study_data[integer_columns] = self.study_data[integer_columns].astype(int)
        float_columns = ["time_of_onset"]
        self.study_data[float_columns] = self.study_data[float_columns].astype(float)

        optional_columns = []
        if "sampling_weights" in self.study_data.columns:
            self.nested_case_control_study = True
            optional_columns.append("sampling_weights")
        if predicted_risk_variable_name is not None:
            self.predicted_risk_variable_name = predicted_risk_variable_name
            optional_columns.append(predicted_risk_variable_name)
        if linear_predictor_variable_name is not None:
            self.linear_predictor_variable_name = linear_predictor_variable_name
            optional_columns.append(linear_predictor_variable_name)
        if len(optional_columns) > 0:
            check_errors.check_data_optional_columns(self.study_data, optional_columns)
            self.study_data[optional_columns] = self.study_data[optional_columns].astype(float)

        if "id" in self.study_data.columns:
            self.study_data.set_index("id", inplace=True)

        if self.nested_case_control_study:
            self.study_data["frequency"] = 1 / self.study_data["sampling_weights"]

        # check data
        check_errors.check_study_data(self.study_data)
        self.study_data["observed_followup"] = self.study_data["study_exit_age"] - self.study_data["study_entry_age"]

        # censor cases where the time of onset is after the observed follow-up period
        onset_after_followup = (self.study_data["observed_outcome"] == 1) & \
                               (self.study_data["time_of_onset"] > self.study_data["observed_followup"])
        self.study_data.loc[onset_after_followup, "observed_outcome"] = 0
        self.study_data.loc[onset_after_followup, "time_of_onset"] = float("inf")

    def _set_predicted_time_interval(self, predicted_risk_interval: Union[str, int, List[int]]) -> None:
        check_errors.check_validation_time_interval_type(predicted_risk_interval, self.study_data)

        if isinstance(predicted_risk_interval, str):
            self.results.set_risk_prediction_interval("Observed follow-up")
            self.study_data["predicted_risk_interval"] = self.study_data["observed_followup"]
        elif isinstance(predicted_risk_interval, int):
            if predicted_risk_interval == 1:
                self.results.set_risk_prediction_interval("1 year")
            else:
                self.results.set_risk_prediction_interval(f"{predicted_risk_interval} years")
            self.study_data["predicted_risk_interval"] = predicted_risk_interval
        else:
            self.study_data["predicted_risk_interval"] = predicted_risk_interval
            if len(self.study_data["predicted_risk_interval"].unique()) == 1:
                self.results.set_risk_prediction_interval(
                    f"{self.study_data['predicted_risk_interval'].unique()[0]} years")
            else:
                self.results.set_risk_prediction_interval("Varies across individuals")

    def _calculate_followup_period(self) -> None:
        self.study_data["followup"] = self.study_data["observed_followup"]

        # follow-up period is the minimum of the predicted risk interval and the observed follow-up period
        onset_within_interval = (self.study_data["time_of_onset"] <= self.study_data["predicted_risk_interval"])
        interval_smaller_than_followup = (self.study_data["predicted_risk_interval"] <=
                                          self.study_data["observed_followup"])
        self.study_data.loc[onset_within_interval & interval_smaller_than_followup, "followup"] = \
            self.study_data.loc[onset_within_interval & interval_smaller_than_followup, "predicted_risk_interval"]

        # censor cases when the time of onset is after the predicted risk interval
        onset_after_interval = (self.study_data["time_of_onset"] > self.study_data["predicted_risk_interval"])
        onset_within_followup = (self.study_data["time_of_onset"] <= self.study_data["observed_followup"])
        self.study_data.loc[onset_after_interval & onset_within_followup, "observed_outcome"] = 0
        self.study_data.loc[onset_after_interval & onset_within_followup, "followup"] = \
            self.study_data.loc[onset_after_interval & onset_within_followup, "predicted_risk_interval"]

        # censor cases when onset is after the observed follow-up period
        observed_longer_than_interval = (self.study_data["observed_followup"] >=
                                         self.study_data["predicted_risk_interval"])
        onset_after_followup = (self.study_data["time_of_onset"] > self.study_data["observed_followup"])
        self.study_data.loc[observed_longer_than_interval & onset_after_followup, "followup"] = \
            self.study_data.loc[observed_longer_than_interval & onset_after_followup, "predicted_risk_interval"]

    def _calculate_risks(self, icare_model_parameters: Optional[dict], predicted_risk_variable_name: Optional[str],
                         linear_predictor_variable_name: Optional[str], seed: Optional[int] = None) -> None:
        if predicted_risk_variable_name is not None and linear_predictor_variable_name is not None:
            if predicted_risk_variable_name in self.study_data.columns and \
                    linear_predictor_variable_name in self.study_data.columns:
                return

        print("\nNote: Both 'predicted_risk_variable_name' and 'linear_predictor_variable_name' were not provided. "
              "They will be calculated using iCARE.")

        absolute_risk_parameters = get_absolute_risk_parameters(icare_model_parameters)
        absolute_risk_parameters["apply_age_start"] = self.study_data["study_entry_age"].tolist()
        absolute_risk_parameters["apply_age_interval_length"] = self.study_data["followup"].tolist()
        absolute_risk_parameters["return_reference_risks"] = True
        absolute_risk_parameters["seed"] = seed

        absolute_risk_model = AbsoluteRiskModel(**absolute_risk_parameters)
        absolute_risk_model.compute_absolute_risks()

        self.predicted_risk_variable_name = "risk_estimates"
        self.study_data["risk_estimates"] = absolute_risk_model.results.risk_estimates.values
        self.linear_predictor_variable_name = "linear_predictors"
        self.study_data["linear_predictors"] = absolute_risk_model.results.linear_predictors.values

    def _calculate_reference_risks(self, icare_model_parameters: Optional[dict],
                                   reference_entry_age: Union[int, List[int], None],
                                   reference_exit_age: Union[int, List[int], None],
                                   reference_predicted_risks: Optional[List[float]],
                                   reference_linear_predictors: Optional[List[float]],
                                   seed: Optional[int] = None) -> None:
        if reference_predicted_risks is not None and reference_linear_predictors is not None:
            check_errors.check_reference_risks(reference_predicted_risks, reference_linear_predictors)
            self.results.set_reference_risks(reference_predicted_risks, reference_linear_predictors)
            return

        age_intervals_provided = reference_entry_age is not None and reference_exit_age is not None

        if not age_intervals_provided:
            return

        print("\nNote: Both 'reference_predicted_risks' and 'reference_linear_predictors' were not provided. "
              "They will be calculated using iCARE.")

        check_errors.check_reference_time_interval_type(reference_entry_age, reference_exit_age)
        if isinstance(reference_entry_age, int):
            reference_followup = reference_exit_age - reference_entry_age
        else:
            reference_followup = [exit_age - entry_age
                                  for entry_age, exit_age in zip(reference_entry_age, reference_exit_age)]

        absolute_risk_parameters = get_absolute_risk_parameters(icare_model_parameters)
        absolute_risk_parameters["apply_age_start"] = reference_entry_age
        absolute_risk_parameters["apply_age_interval_length"] = reference_followup
        absolute_risk_parameters["covariate_profile_path"] = absolute_risk_parameters["reference_dataset_path"]
        absolute_risk_parameters["snp_profile_path"] = None
        absolute_risk_parameters["return_reference_risks"] = True
        absolute_risk_parameters["seed"] = seed

        absolute_risk_model = AbsoluteRiskModel(**absolute_risk_parameters)
        absolute_risk_model.compute_absolute_risks()

        reference_predicted_risks = absolute_risk_model.results.risk_estimates.values
        reference_linear_predictors = absolute_risk_model.results.linear_predictors.values
        self.results.set_reference_risks(reference_predicted_risks, reference_linear_predictors)

    def _calculate_study_incidence_rates(self, icare_model_parameters: Optional[dict]) -> None:
        age_specific_study_incidence = []

        age_of_onset = self.study_data["study_entry_age"] + self.study_data["time_of_onset"]
        ages = range(self.study_data["study_entry_age"].min() + 1, self.study_data["study_exit_age"].max())
        frequency = self.study_data["frequency"].values \
            if self.nested_case_control_study else np.ones(len(self.study_data))

        for age in ages:
            entered_before_age = self.study_data["study_entry_age"] <= age - 1
            not_exited_before_age = self.study_data["study_exit_age"] >= age
            in_study_at_age = entered_before_age & not_exited_before_age
            onset_at_age = (age_of_onset >= age) & (age_of_onset < age + 1)
            onset_at_or_after_age = age_of_onset >= age

            num_onsets_at_age = np.sum((in_study_at_age & onset_at_age) @ frequency)
            num_in_study_at_age = np.sum((in_study_at_age & onset_at_or_after_age) @ frequency)

            incidence_at_age = num_onsets_at_age / num_in_study_at_age if num_in_study_at_age > 0 else np.nan
            age_specific_study_incidence.append(incidence_at_age)

        population_incidence_rates_path = None
        if icare_model_parameters is not None:
            if "model_disease_incidence_rates_path" in icare_model_parameters:
                population_incidence_rates_path = icare_model_parameters["model_disease_incidence_rates_path"]
        self.results.set_incidence_rates(list(ages), age_specific_study_incidence, population_incidence_rates_path)
