import pathlib
from typing import Union, List, Optional

from icare import misc
from icare.absolute_risk_model import AbsoluteRiskModel


def compute_absolute_risk(apply_age_start: Union[int, List[int]],
                          apply_age_interval_length: Union[int, List[int]],
                          model_disease_incidence_rates_path: Union[str, pathlib.Path],
                          model_competing_incidence_rates_path: Union[str, pathlib.Path, None] = None,
                          model_covariate_formula_path: Union[str, pathlib.Path, None] = None,
                          model_log_relative_risk_path: Union[str, pathlib.Path, None] = None,
                          model_reference_dataset_path: Union[str, pathlib.Path, None] = None,
                          model_reference_dataset_weights_variable_name: Optional[str] = None,
                          model_snp_info_path: Union[str, pathlib.Path, None] = None,
                          model_family_history_variable_name: Optional[str] = None,
                          num_imputations: int = 5,
                          apply_covariate_profile_path: Union[str, pathlib.Path, None] = None,
                          apply_snp_profile_path: Union[str, pathlib.Path, None] = None,
                          return_linear_predictors: bool = False,
                          return_reference_risks: bool = False) -> dict:
    """
    This function is used to build absolute risk models and apply them to estimate absolute risks.

    :param apply_age_start: Age(s) for the start of the interval, over which, to compute the absolute risk. If a single
        integer is provided, all instances in the profiles ('apply_covariate_profile_path' and/or
        'apply_snp_profile_path') are assigned this start age for the interval. If a different start age needs to be
        assigned for each instance, provide a list of ages as integers of the same length as the number of instances in
        these profiles.
    :param apply_age_interval_length: Number of years over which to compute the absolute risk. That is to say that the
        age at the end of the interval is 'apply_age_start' + 'apply_age_interval_length'. If a single integer is
        provided, all instances in the profiles ('apply_covariate_profile_path' and/or 'apply_snp_profile_path') are
        assigned this interval length. If a different interval length needs to be assigned for each instance, provide a
        list of interval lengths as integers of the same length as the number of instances in these profiles.
    :param model_disease_incidence_rates_path:
        A path to a CSV file containing the age-specific disease incidence rates for the population of interest. The
        data in the file must either contain two columns, named: ['age', 'rate'], to specify the incidence rates
        associated with each age group; or three columns, named: ['start_age', 'end_age', 'rate'], to specify the
        incidence rates associated with each age interval. The age ranges must fully cover the age intervals specified
        using parameters 'apply_age_start' and 'apply_age_interval_length'.
    :param model_competing_incidence_rates_path:
        A path to a CSV file containing the age-specific incidence rates for competing events in the population of
        interest. The data in the file must either contain two columns, named: ['age', 'rate'], to specify the
        incidence rates associated with each age group; or three columns, named: ['start_age', 'end_age', 'rate'], to
        specify the incidence rates associated with each age interval. The age ranges must fully cover the age
        intervals specified using parameters 'apply_age_start' and 'apply_age_interval_length'.
    :param model_covariate_formula_path:
        A path to a text file containing a Patsy symbolic description string of the model to be fitted,
        e.g. Y ~ parity + family_history.
        Reference: https://patsy.readthedocs.io/en/latest/formulas.html#the-formula-language
        Please make sure that the variable name in your dataset is not from the namespace of the Python execution
        context, including Python standard library, numpy, pandas, patsy, and icare. For example, a variable name "C"
        and "Q" would conflict with Patsy built-in functions of the same name. Variable names with the R-style periods
        in them should be surrounded by the Patsy quote function Q(family.history). In Python, periods are used to
        access attributes of objects, so they are not allowed in Patsy variable names unless surrounded by Q().
        Patsy language is similar to R's formula object (https://patsy.readthedocs.io/en/latest/R-comparison.html).
    :param model_log_relative_risk_path:
        A path to a JSON file containing the log odds ratios, of the variables in the model except the intercept term,
        in association with the disease. The first-level JSON keys should correspond to the variable names generated by
        Patsy when building the design matrix. Their values should correspond to the log odds ratios of the variable's
        association with the disease.
    :param model_reference_dataset_path:
        A path to a CSV file containing the reference dataset with risk factor distribution that is representative of
        the population of interest. No missing values are permitted in this dataset.
    :param model_reference_dataset_weights_variable_name:
        A string specifying the name of the variable in the dataset at 'model_reference_dataset_path' that indicates
        the sampling weight for each instance. If set to None (default), then a uniform weight will be assigned to each
        instance.
    :param model_snp_info_path:
        A path to a CSV file containing the information about the SNPs in the model. The data should contain three
        columns, named: ['snp_name', 'snp_odds_ratio', 'snp_freq'] corresponding to the SNP ID, the odds ratio of the
        SNP in association with the disease, and the minor allele frequency, respectively.
    :param model_family_history_variable_name:
        A string specifying the name of the binary variable (values: {0, 1}; missing values are permitted) in the
        model formula ('model_covariate_formula_path') that represents the family history of the disease. This needs to
        be specified when using the special SNP model option so that the effect of family history can be adjusted for
        the presence of the SNPs.
    :param num_imputations:
        The number of imputations for handling missing SNPs.
    :param apply_covariate_profile_path:
        A path to a CSV file containing the covariate (risk factor) profiles of the individuals for whom the absolute
        risk is to be computed. Missing values are permitted.
    :param apply_snp_profile_path:
        A path to a CSV file containing the SNP profiles (values: {0: homozygous reference alleles, 1: heterozygous,
        2: homozygous alternate alleles}) of the individuals for whom the absolute risk is to be computed. Missing
        values are permitted.
    :param return_linear_predictors:
        Set True to return the calculated linear predictor values for each individual in the
        'apply_covariate_profile_path' and/or 'apply_snp_profile_path' datasets.
    :param return_reference_risks:
        Set True to return the absolute risk estimates for each individual in the 'model_reference_dataset_path'
        dataset.
    :return:
        A dictionary with the following keys—
            1) 'model':
                A dictionary of feature names and the associated beta values that were used to compute the absolute risk
                estimates.
                A Pandas Series can be reconstructed using the following code:
                    import pandas as pd
                    results = compute_absolute_risk(...)
                    pd.Series(results["model"])
            2) 'profile':
                A records-oriented JSON of the input profile data, the specified age intervals, and the calculated
                absolute risk estimates. If 'return_linear_predictors' is set to True, they are also included as an
                additional column.
                A Pandas DataFrame can be reconstructed using the following code:
                    import pandas as pd
                    results = compute_absolute_risk(...)
                    pd.read_json(results["profile"], orient="records")
            3) 'reference_risks':
                If 'return_reference_risks' is True, this key will be present in the returned dictionary. It will
                contain a list of dictionaries, one per unique combination of the specified age intervals, containing
                age at the start of interval ('age_interval_start'), age at the end of interval ('age_interval_end'),
                and a list absolute risk estimates for the individuals in the reference dataset ('population_risks').
    """

    absolute_risk_model = AbsoluteRiskModel(
        apply_age_start, apply_age_interval_length, model_disease_incidence_rates_path, model_covariate_formula_path,
        model_snp_info_path, model_log_relative_risk_path, model_reference_dataset_path,
        model_reference_dataset_weights_variable_name, model_competing_incidence_rates_path,
        model_family_history_variable_name, num_imputations, apply_covariate_profile_path, apply_snp_profile_path,
        return_reference_risks)

    absolute_risk_model.compute_absolute_risks()

    return misc.package_absolute_risk_results_to_dict(absolute_risk_model, return_linear_predictors,
                                                      return_reference_risks)


def compute_absolute_risk_split_interval(apply_age_start: Union[int, List[int]],
                                         apply_age_interval_length: Union[int, List[int]],
                                         apply_cov_profile,
                                         model_formula,
                                         model_disease_incidence_rates,
                                         model_log_rr,
                                         model_ref_dataset,
                                         model_cov_info,
                                         model_ref_dataset_weights=None,
                                         model_competing_incidence_rates=None,
                                         apply_snp_profile=None,
                                         model_snp_info=None,
                                         model_bin_fh_name=None,
                                         cut_time=None,
                                         apply_cov_profile_2=None,
                                         model_formula_2=None,
                                         model_log_rr_2=None,
                                         model_ref_dataset_2=None,
                                         model_ref_dataset_weights_2=None,
                                         model_cov_info_2=None,
                                         model_bin_fh_name_2=None,
                                         num_imputations=5,
                                         return_linear_predictors: bool = False,
                                         return_reference_risks: bool = False) -> dict:
    """
    This function is used to build an absolute risk model that incorporates different input parameters before and after
        a given time point. The model is then applied to estimate absolute risks.

    :param return_linear_predictors:
        Set True to return the calculated linear predictor values for each individual in the
        'apply_covariate_profile_path' and/or 'apply_snp_profile_path' datasets.
    :param return_reference_risks:
        Set True to return the absolute risk estimates for each individual in the 'model_reference_dataset_path'
        dataset.
    """
    pass


def validate_absolute_risk_model(study_data_path: Union[str, pathlib.Path],
                                 predicted_risk_interval: Union[str, int, List[int]],
                                 icare_model_parameters: Optional[dict] = None,
                                 predicted_risk_variable_name: Optional[str] = None,
                                 linear_predictor_variable_name: Optional[str] = None,
                                 reference_entry_age: Union[int, List[int], None] = None,
                                 reference_exit_age: Union[int, List[int], None] = None,
                                 reference_predicted_risks: Optional[List[float]] = None,
                                 reference_linear_predictors: Optional[List[float]] = None,
                                 number_of_percentiles: int = 10,
                                 linear_predictor_cutoffs: Optional[List[float]] = None,
                                 dataset_name: str = "Example dataset",
                                 model_name: str = "Example risk prediction model") -> dict:
    """
    This function is used to validate absolute risk models.

    :param study_data_path:
        A path to a CSV file containing the study data. The data must contain the following columns:
            1) 'observed_outcome': the disease status { 0: censored; 1: disease occurred by the end of the follow-up
                period },
            2) 'study_entry_age': age (in years) when entering the cohort,
            3) 'study_exit_age': age (in years) at last follow-up visit,
            4) 'time_of_onset': time (in years) from study entry to disease onset; note that all subjects are
                disease-free at the time of entry and those individuals who do not develop the disease by the end of
                the follow-up period are considered censored, and this value is set to 'inf'.
            5) 'sampling_weights': for a case-control study nested within a cohort study, this is column is provided to
                indicate the probability of the inclusion of that individual into the nested case-control study. If the
                study is not a nested case-control study, do not include this column in the study data.
    :param predicted_risk_interval:
        If the risk validation is to be performed over the total follow-up period, set this parameter to the string
        'total-followup'. Otherwise, it should be set to either an integer or a list of integers representing the
        number of years after study entry over which, the estimated risk is being validated. Example: 5 for a 5-year
        risk validation.
    :param icare_model_parameters:
        A dictionary containing the parameters of the absolute risk model to be validated. The keys of the dictionary
        are the parameters of the 'compute_absolute_risk' function. If the risk prediction being validated is from a
        method other than iCARE, this parameter should be set to None and the 'predicted_risk_variable_name' and
        'linear_predictor_variable_name' parameters should be set to the names of the columns containing the risk
        predictions and linear predictor values, respectively, in the study data.
    :param predicted_risk_variable_name:
        If the risk prediction is to be done by iCARE (i.e. using the compute_absolute_risk() method), set this value
        to None. Else, supply the risk predictions for each individual in the study data, using some other method,
        as an additional column in the study data. The name of that column should be supplied here as a string.
    :param linear_predictor_variable_name:
        The linear predictor is a risk score for an individual calculated as: Z * beta. Here, Z is a vector of risk
        factor values for that individual and beta is a vector of log relative risks. If the linear predictor values are
        to be calculated by iCARE (i.e. using the compute_absolute_risk() method), set this value to None. Else, supply
        the linear predictor values for each individual in the study data as an additional column in the study data.
        The name of that column should be supplied here.
    :param reference_entry_age:
        Specify an integer or a list of integers, representing the ages at entry for the reference population, to
        compute their absolute risks. If both 'reference_predicted_risks' and 'reference_linear_predictors' are
        provided, this parameter is ignored.
    :param reference_exit_age:
        Specify an integer or a list of integers, representing the ages at exit for the reference population, to
        compute their absolute risks. If both 'reference_predicted_risks' and 'reference_linear_predictors' are
        provided, this parameter is ignored.
    :param reference_predicted_risks:
        A list of absolute risk estimates for the reference population assuming the entry ages specified at
        'reference_entry_age' and exit ages specified at 'reference_exit_age'. If both this parameter and
        'reference_linear_predictors' are provided, they are not re-computed using the compute_absolute_risk() method.
    :param reference_linear_predictors:
        A list of linear predictor values for the reference population assuming the entry ages specified at
        'reference_entry_age' and exit ages specified at 'reference_exit_age'. If both this parameter and
        'reference_predicted_risks' are provided, they are not re-computed using the compute_absolute_risk() method.
    :param number_of_percentiles:
        The number of percentiles of the risk score that determines the number of strata over which, the risk
        prediction model is to be validated.
    :param linear_predictor_cutoffs:
        A list of user specified cut-points for the linear predictor to define categories for absolute risk calibration
        and relative risk calibration.
    :param dataset_name:
        Name of the validation dataset, e.g., "PLCO full cohort" or "Full cohort simulation".
    :param model_name:
        Name of the absolute risk model being validated, e.g., "Synthetic model" or "Simulation setting".
    """
    from icare.model_validation import ModelValidation

    # compute_absolute_risk(**icare_model_parameters)
    model_validation = ModelValidation(study_data_path, predicted_risk_interval, icare_model_parameters,
                                       predicted_risk_variable_name, linear_predictor_variable_name,
                                       reference_entry_age, reference_exit_age, reference_predicted_risks,
                                       reference_linear_predictors, number_of_percentiles, linear_predictor_cutoffs,
                                       dataset_name, model_name)

    return misc.package_validation_results_to_dict(model_validation)
