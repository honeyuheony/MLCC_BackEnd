from rest_framework.generics import ListAPIView, RetrieveAPIView
from django.shortcuts import get_object_or_404 as _get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from asgiref.sync import sync_to_async

from datetime import datetime, timedelta, date
from django.db.models import Avg

from .models import Data, Bbox, Margin
from .serializers import DataSerializer, BboxSerializer, MarginSerializer
from .tasks import *
# Main Page


@api_view(['GET'])
def main(request):
    queryset = Data.objects.all()
    threshold = request.query_params.get('threshold')
    period = request.query_params.get('period')
    if period is not None:
        from_date, to_date = period.split('~')
        from_date = list(map(int, from_date.split('.')))
        to_date = list(map(int, to_date.split('.')))
        queryset = queryset.filter(
            created_date__range=[date(from_date[0], from_date[1], from_date[2]), date(to_date[0], to_date[1], to_date[2])])
    else:
        yesterday, today = datetime.today() - timedelta(1), datetime.today()
        queryset = queryset.filter(
            created_date__range=[yesterday, today])
    if threshold is None:
        threshold = 85
    # SELECT ... WHERE margin_ratio >= threshold
    normal = queryset.filter(margin_ratio__gte=threshold)
    # SELECT ... WHERE margin_ratio < threshold
    error = queryset.filter(margin_ratio__lt=threshold)
    normal = DataSerializer(normal, many=True, context={
                            'request': request}).data
    error = DataSerializer(error, many=True, context={
        'request': request}).data
    result = {
        "Normal": normal,
        "Error": error
    }
    return Response(result, headers={"description": "SUCCESS"})

# Detail


@api_view(['GET'])
def detail(request, name):
    threshold = request.query_params.get('threshold')

    # Data, Bbox Query and Serializer
    data = DataSerializer(Data.objects.get(name=name),
                          context={'request': request}).data
    bbox = BboxSerializer(
        Bbox.objects.all().filter(data=name), many=True).data

    ratio = {}
    bbox_data = {}
    margin_list = {}

    for b in bbox:
        bbox_name = b['name']
        ratio[bbox_name] = b['min_margin_ratio']
        b.pop('name')
        b.pop('data')
        b.pop('min_margin_ratio')
        bbox_data[bbox_name] = b
        margin_data = MarginSerializer(
            Margin.objects.all().filter(bbox=bbox_name), many=True).data
        for m in margin_data:
            m.pop('name')
            m.pop('bbox')
        margin_list[bbox_name] = margin_data

    result = {
        "Original_img": data['original_image'],
        "Segmentation_img": data['segmentation_image'],
        "Box": bbox_data,
        "Ratio": ratio,
        "Margin_list": margin_list,
    }

    return Response(result, headers={"description": "SUCCESS"})

# Data


class DataListView(ListCreateAPIView):
    def get_normal_queryset(self):
        queryset = Data.objects.all()
        threshold = self.request.query_params.get('threshold')
        if threshold is not None:
            # SELECT ... WHERE margin_ratio >= threshold
            queryset = queryset.filter(margin_ratio__gte=threshold)
        return queryset

    queryset = Data.objects.all()
    serializer_class = DataSerializer


class DataRetrieveView(RetrieveUpdateDestroyAPIView):
    queryset = Data.objects.all()
    serializer_class = DataSerializer

# Bbox


class BboxListView(ListCreateAPIView):
    queryset = Bbox.objects.all()
    serializer_class = BboxSerializer


class BboxRetrieveView(RetrieveUpdateDestroyAPIView):
    queryset = Bbox.objects.all()
    serializer_class = BboxSerializer
    # lookup_fields = ['data']

# Margin


class MarginListView(ListCreateAPIView):
    queryset = Margin.objects.all()
    serializer_class = MarginSerializer


class MarginRetrieveView(RetrieveUpdateDestroyAPIView):
    queryset = Margin.objects.all()
    serializer_class = MarginSerializer
    # lookup_fields = ['bbox']
