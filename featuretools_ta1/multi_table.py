from d3m.metadata import base as metadata_base, hyperparams, params
from d3m import container, exceptions
from d3m.base import utils as d3m_utils


from d3m.primitive_interfaces.unsupervised_learning import UnsupervisedLearnerPrimitiveBase
from typing import Dict, Optional, Union
from featuretools_ta1 import config as CONFIG
from d3m.primitive_interfaces.base import CallResult, DockerContainer
from d3m.exceptions import PrimitiveNotFittedError
from featuretools_ta1.utils import drop_percent_null, select_one_of_correlated
import featuretools_ta1
import featuretools as ft
import numpy as np
import typing
import pandas as pd
import featuretools_ta1.semantic_types as st
from featuretools_ta1.utils import add_metadata, find_primary_key, find_target_column, get_featuretools_variable_types

Inputs = container.Dataset
Outputs = container.DataFrame
TARGET_ENTITY = "table"

class Params(params.Params):
    # A named tuple for parameters.
    features: Optional[bytes]

# todo target entity


class Hyperparams(hyperparams.Hyperparams):
    target_resource = hyperparams.Hyperparameter[typing.Union[str, None]](
        default=None,
        semantic_types=['https://metadata.datadrivendiscovery.org/types/ControlParameter'],
        description="The resource to create features for. If \"None\" then it starts from the dataset entry point.",
    )
    max_depth = hyperparams.Hyperparameter[int](
        default=2,
        description='The maximum number of featuretools primitives to stack when creating features',
        semantic_types=['https://metadata.datadrivendiscovery.org/types/TuningParameter']
    )
    max_percent_null = hyperparams.Bounded[float](
        default=.5,
        lower=0,
        upper=1,
        description='The maximum percentage of null values allowed in returned features. A lower value means features may have more null nulls.',
        semantic_types=['https://metadata.datadrivendiscovery.org/types/TuningParameter']
    )
    max_correlation = hyperparams.Bounded[float](
        default=.9,
        lower=0,
        upper=1,
        description='The maximum allowed correlation between any two features returned. A lower value means features will be more uncorrelated',
        semantic_types=['https://metadata.datadrivendiscovery.org/types/TuningParameter']
    )
    use_columns = hyperparams.Set(
        elements=hyperparams.Hyperparameter[int](-1),
        default=(),
        semantic_types=['https://metadata.datadrivendiscovery.org/types/ControlParameter'],
        description="A set of column indices to force primitive to operate on. If any specified column cannot be parsed, it is skipped.",
    )
    exclude_columns = hyperparams.Set(
        elements=hyperparams.Hyperparameter[int](-1),
        default=(),
        semantic_types=['https://metadata.datadrivendiscovery.org/types/ControlParameter'],
        description="A set of column indices to not operate on. Applicable only if \"use_columns\" is not provided.",
    )
    return_result = hyperparams.Enumeration(
        values=['append', 'replace', 'new'],
        default='new',
        semantic_types=['https://metadata.datadrivendiscovery.org/types/ControlParameter'],
        description="Should parsed columns be appended, should they replace original columns, or should only parsed columns be returned? This hyperparam is ignored if use_semantic_types is set to false.",
    )


class MultiTableFeaturization(UnsupervisedLearnerPrimitiveBase[Inputs, Outputs, Params, Hyperparams]):
    """This primitive creates new interaction features for an input dataframe.

    After creating features it reduces the set of possible features using an unsupervised approach"""
    __author__ = 'Max Kanter <max.kanter@featurelabs.com>'
    metadata = metadata_base.PrimitiveMetadata(
        {
            'id': 'e659ef3a-f17c-4bbf-9e5a-13de79a4e55b',
            'version': featuretools_ta1.__version__,
            'name': "Multi Table Deep Feature Synthesis",
            'python_path': 'd3m.primitives.feature_construction.deep_feature_synthesis.MultiTableFeaturization',
            'source': {
                'name': CONFIG.AUTHOR,
                'contact': CONFIG.CONTACT,
                'uris': ['https://docs.featuretools.com'],
                'license': 'BSD-3-Clause'
            },
            'installation': CONFIG.INSTALLATION,
            'algorithm_types': [
                metadata_base.PrimitiveAlgorithmType.DEEP_FEATURE_SYNTHESIS,
            ],
            'primitive_family': metadata_base.PrimitiveFamily.FEATURE_CONSTRUCTION,
            'keywords': [
                'featurization',
                'feature engineering',
                'feature extraction',
                'feature construction'
            ],
            'hyperparameters_to_tune': ['max_percent_null', 'max_correlation'],
        },
    )

    def __init__(self, *,
                 hyperparams: Hyperparams,
                 random_seed: int = 0,
                 docker_containers: Dict[str, DockerContainer] = None) -> None:
        self._fitted = False

        # chunk size for feature calculation
        self.chunk_size = .5

        # todo handle use_columns, exclude_columns
        # todo handle return result

        super().__init__(hyperparams=hyperparams, random_seed=random_seed, docker_containers=docker_containers)

    def set_training_data(self, *, inputs: Inputs) -> None:
        self._target_resource_id, _ = d3m_utils.get_tabular_resource(inputs, self.hyperparams["target_resource"])
        # d3m.base.utils.
        self._inputs = inputs
        self._fitted = False

    def fit(self, *, timeout: float = None, iterations: int = None) -> CallResult[None]:
        es = self._make_entityset(self._inputs)

        ignore_variables = {}

        # if there is a target column on the target entity, ignore it
        target_column = find_target_column(self._inputs[self._target_resource_id], return_index=False)
        if target_column:
            ignore_variables = {self._target_resource_id: [target_column]}

        # generate all the features
        fm, features = ft.dfs(
            target_entity=self._target_resource_id,
            entityset=es,
            agg_primitives=["mean", "sum", "count", "mode", "num_unique"],
            trans_primitives=["day", "week", "month", "year", "num_words", "num_characters"],
            max_depth=self.hyperparams["max_depth"],
            verbose=True,
            chunk_size=self.chunk_size,
            ignore_variables=ignore_variables
        )

        # treat inf as null. repeat in produce step
        fm = fm.replace([np.inf, -np.inf], np.nan)

        # filter based on nulls and correlation
        fm, features = drop_percent_null(fm, features, max_percent_null=self.hyperparams['max_percent_null'])
        fm, features = select_one_of_correlated(fm, features, threshold=self.hyperparams['max_correlation'])

        self.features = features

        self._fitted = True

        return CallResult(None)

    def produce(self, *, inputs: Inputs, timeout: float = None, iterations: int = None) -> CallResult[Outputs]:
        if not self._fitted:
            raise PrimitiveNotFittedError("Primitive not fitted.")

        es = self._make_entityset(inputs.copy())

        fm = ft.calculate_feature_matrix(
            entityset=es,
            features=self.features,
            chunk_size=self.chunk_size,
            verbose=True
        )

        # make sure the feature matrix is ordered the same as the input
        fm = fm.reindex(es[self._target_resource_id].df.index)

        # treat inf as null like fit step
        fm = fm.replace([np.inf, -np.inf], np.nan)

        # todo add this metadata handle
        fm = add_metadata(fm, self.features)

        target_index = find_target_column(inputs[self._target_resource_id], return_index=True)

        # if a target is found,
        if target_index:
            labels = self._inputs[self._target_resource_id].select_columns([target_index])
            labels.index = fm.index # assumes labels are align the same as feature matrix
            fm = fm.append_columns(labels)

        return CallResult(fm)

    def get_params(self) -> Params:
        if not self._fitted:
            return Params(features=None)

        return Params(features=None)

    def set_params(self, *, params: Params) -> None:
        self.features = params["features"]

        # infer if it is fitted
        if self.features:
            self._fitted = True


    def _make_entityset(self, input):
        es = ft.EntitySet()
        resources = self._inputs.items()
        for resource_id, resource_df in resources:
            # make sure resources is a dataframe
            if not isinstance(resource_df, container.DataFrame):
                continue

            primary_key = find_primary_key(resource_df)

            if primary_key is None:
                raise RuntimeError("Cannot find primary key in resource %s" % (str(resource_id)))

            variable_types = get_featuretools_variable_types(resource_df)

            # todo: this should probably be removed because type conversion should happen outside primitive
            # resource_df[col_name] = resource_df[col_name].astype(metadata['structural_type'])
            es.entity_from_dataframe(
                entity_id=resource_id,
                index=primary_key,
                dataframe=pd.DataFrame(resource_df),
                variable_types=variable_types
            )


        # relations is a dictionary mapping resource to
        # (other resource, direction (true if other resource is parent, false if child), key resource index, other resource index)
        relations = self._inputs.get_relations_graph()
        for entity in es.entities:
            # only want relationships in child to parent direction
            relationships = [r for r in relations[entity.id] if r[1]]

            for rel in relationships:
                parent_entity_id = rel[0]
                parent_variable_id = self._inputs.metadata.query([parent_entity_id, "ALL_ELEMENTS", rel[3]])["name"]
                child_entity_id = entity.id
                child_variable_id = self._inputs.metadata.query([child_entity_id, "ALL_ELEMENTS", rel[2]])["name"]
                es.add_relationship(
                    ft.Relationship(
                        es[parent_entity_id][parent_variable_id],
                        es[child_entity_id][child_variable_id]
                    )
                )

        return es






