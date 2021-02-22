# Copyright (c) Microsoft Corporation. All rights reserved.
""" Contains data preparation inspectors that can be used in Azure Machine Learning.

An inspector collects specific statistics on specified columns of a :class:`azureml.dataprep.Dataflow`, which
can be used to understand the input data. Create an inspector and execute it with the 
Dataflow class ``execute_inspector`` method. You can execute multiple Inspector objects with the
``execute_inspectors`` method.
"""

from .engineapi.api import EngineAPI
from .engineapi.typedefinitions import (ActivityReference, ExecuteInspectorCommonArguments, ExecuteInspectorsMessageArguments, InspectorArguments, ColumnsSelector, StaticColumnsSelectorDetails, DynamicColumnsSelectorDetails, SingleColumnSelectorDetails, ColumnsSelectorType)
from typing import Any, Dict, List, Tuple, Union
from uuid import uuid4
import json

_MAX_ROW_COUNT = 2**31 - 1

#TODO: These inspectors will eventually be auto-generated - Feature 474399: Codegen for dataprep SDK inspectors in engine (https://msdata.visualstudio.com/Vienna/_workitems/edit/474399/)
class BaseInspector:
    """Represents the base inspector.
    """

    def __init__(self):
        pass

    def _to_inspector_arguments(self):
        pass

class TableInspector(BaseInspector):
    """Defines an inspector that returns summary statistics on all the data represented by a Dataflow.
    """

    def __init__(self,
        includeSTypeCounts: bool,
        includeAverageSpacesCount: bool,
        includeStringLengths: bool,
        numberOfHistogramBins: int = 10
    ):
        self.includeSTypeCounts = includeSTypeCounts
        self.includeAverageSpacesCount = includeAverageSpacesCount
        self.includeStringLengths = includeStringLengths
        self.numberOfHistogramBins = numberOfHistogramBins

    def _to_inspector_arguments(self):
        return InspectorArguments(inspector_type='Microsoft.DPrep.TableInspector',
        arguments={
            "includeSTypeCounts": self.includeSTypeCounts,
            "includeAverageSpacesCount": self.includeAverageSpacesCount,
            "includeStringLengths": self.includeStringLengths,
            "numberOfHistogramBins": self.numberOfHistogramBins if self.numberOfHistogramBins is not None else None
        })

class ValueCountInspector(BaseInspector):
    """Defines an inspector that returns value counts for the specified column.
    """

    def __init__(self,
        columnId: str,
        descending: bool = True,
        includeNulls: bool= True,
        haloEffect: bool = True,
        logScale: bool = False,
        numberOfTopValues: int = 6
    ):
        self.columnId = columnId
        self.numberOfTopValues = numberOfTopValues
        self.descending = descending
        self.includeNulls = includeNulls
        self.haloEffect = haloEffect
        self.logScale = logScale

    def _to_inspector_arguments(self):
        return InspectorArguments(inspector_type='Microsoft.DPrep.ValueCountInspector',
        arguments={
            "columnId": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.columnId),
                    type = ColumnsSelectorType.SINGLECOLUMN),
            "numberOfTopValues": self.numberOfTopValues,
            "descending": self.descending,
            "includeNulls": self.includeNulls,
            "haloEffect": self.haloEffect,
            "logScale": self.logScale,
        })

class HistogramInspector(BaseInspector):
    """Defines an inspector that returns histogram data for the specified column.
    """

    def __init__(self,
        columnId: str,
        defaultBucketing: bool,
        haloEffect: bool,
        densityPlot: bool,
        logScale: bool,
        numberOfBreaks: int = None
    ):
        self.columnId = columnId
        self.defaultBucketing = defaultBucketing
        self.haloEffect = haloEffect
        self.densityPlot = densityPlot
        self.logScale = logScale
        self.numberOfBreaks = numberOfBreaks
        self.columnsSelectorType = ColumnsSelectorType.SINGLECOLUMN

    def _to_inspector_arguments(self):
        return InspectorArguments(inspector_type='Microsoft.DPrep.HistogramInspector',
        arguments={
            "columnId": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.columnId),
                    type = self.columnsSelectorType),
            "defaultBucketing": self.defaultBucketing,
            "haloEffect": self.haloEffect,
            "densityPlot": self.densityPlot,
            "logScale": self.logScale,
            "numberOfBreaks": self.numberOfBreaks if self.numberOfBreaks is not None else None
        })

class BoxAndWhiskerInspector(BaseInspector):
    """Defines an inspector that returns box and whisker plot data for the specified column.
    """

    def __init__(self,
        columnId: str,
        columnsSelectorType: str = ColumnsSelectorType.SINGLECOLUMN,
        groupByColumn: str = None
    ):
        self.columnId = columnId
        self.columnsSelectorType = columnsSelectorType
        self.groupByColumn = groupByColumn

    def _to_inspector_arguments(self):
        return InspectorArguments(inspector_type='Microsoft.DPrep.BoxAndWhiskerInspector',
        arguments={
            "columnId": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.columnId),
                    type = self.columnsSelectorType),
            "groupByColumn": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.groupByColumn),
                    type = self.columnsSelectorType) if self.groupByColumn is not None else None
        })

class ColumnStatsInspector(BaseInspector):
    """Defines an inspector that returns column stats for the specified column.
    """

    def __init__(self,
        columnId: str
    ):
        self.columnId = columnId
    def _to_inspector_arguments(self):
        return InspectorArguments(inspector_type='Microsoft.DPrep.ColumnStatsInspector',
        arguments={
            "columnId": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.columnId),
                    type = ColumnsSelectorType.SINGLECOLUMN)
        })

class ScatterPlotInspector(BaseInspector):
    """Defines an inspector that returns data for a scatter plot for the specified axes.
    """

    def __init__(self,
        xAxisColumn: str,
        yAxisColumn: str,
        probability: float,
        seed: int,
        groupByColumn: str = None,
        
    ):
        self.xAxisColumn = xAxisColumn
        self.yAxisColumn = yAxisColumn
        self.probability = probability
        self.seed = seed
        self.groupByColumn = groupByColumn

    def _to_inspector_arguments(self):
        return InspectorArguments(inspector_type='Microsoft.DPrep.ScatterPlotInspector',
        arguments={
            "xAxisColumn": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.xAxisColumn),
                    type = ColumnsSelectorType.SINGLECOLUMN),
            "yAxisColumn": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.yAxisColumn),
                    type = ColumnsSelectorType.SINGLECOLUMN),
            "probability": self.probability,
            "seed": self.seed,
            "groupByColumn": ColumnsSelector(
                details = SingleColumnSelectorDetails(
                    selected_column = self.groupByColumn),
                    type = ColumnsSelectorType.SINGLECOLUMN) if self.groupByColumn is not None else None
        })

class _Inspector:
    @classmethod
    def _from_execution(
        cls,
        engine_api: EngineAPI,
        context: ActivityReference,
        inspector: Union[str, BaseInspector]):

        if isinstance(inspector, BaseInspector):
            inspector_arguments = inspector._to_inspector_arguments()
        elif isinstance(inspector, str):
            inspector_arguments = json.loads(inspector)
        else:
            inspector_arguments = inspector

        return engine_api.execute_inspector(ExecuteInspectorCommonArguments(
            context = context,
            inspector_arguments = inspector_arguments,
            offset = 0,
            row_count = _MAX_ROW_COUNT))

class _InspectorBatch:
    # inspector_id corresponds to a GUID that is used to match the requested
    # InspectorArguments as a key and the content in the Inspector as a value 
    # due to objects being unable to be stored as keys for a dictionary in JSON
    @classmethod
    def _from_execution(
        cls,
        engine_api: EngineAPI,
        context: ActivityReference,
        inspectors: Union[str, List[BaseInspector]]):
        if isinstance(inspectors, str):
            inspectors = json.loads(inspectors)
            request = [ExecuteInspectorsMessageArguments(
            inspector_arguments = ExecuteInspectorCommonArguments(
                context = context,
                inspector_arguments = inspector,
                offset = 0,
                row_count = _MAX_ROW_COUNT),
            inspector_id = uuid4()
            ) for inspector in inspectors]

            response = engine_api.execute_inspectors(request)

            result = {}
            for inspector_response in request:
                result[inspector_response.inspector_arguments.inspector_arguments] = response[inspector_response.inspector_id]  
            return result

        elif isinstance(inspectors, List):
            request = []
            inspector_dict = {}
            for inspector in inspectors:
                guid = uuid4()
                inspector_dict[str(guid)] = inspector
                request.append(ExecuteInspectorsMessageArguments(
                    inspector_arguments = ExecuteInspectorCommonArguments(
                    context = context,
                    inspector_arguments = inspector._to_inspector_arguments(),
                    offset = 0,
                    row_count = _MAX_ROW_COUNT),
                inspector_id = guid
                ))
                
            response = engine_api.execute_inspectors(request)

            result = {}
            for inspector_response in request:
                result[inspector_dict[inspector_response.inspector_id]] = response[inspector_response.inspector_id]  
            return result

