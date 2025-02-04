from django.conf import settings
from rest_framework.generics import ListAPIView, RetrieveAPIView
from django.shortcuts import get_object_or_404 as _get_object_or_404
from django.core.exceptions import ValidationError
from django.http import Http404
from django.db import transaction

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from asgiref.sync import sync_to_async

from datetime import datetime, timedelta, date
from django.db.models import Avg

from .models import Data, Bbox, ManualLog, Margin, State, InferencePath
from .serializers import DataSerializer, BboxSerializer, ManualLogSerializer, MarginSerializer
from celery.schedules import crontab
from .tasks import model_lock
import os, shutil, sys, time, random, argparse
sys.path.append("C:/Users/user/Desktop/IITP/mmcv_laminate_alignment_system")
from mlcc_self_train_eval import self_train_eval


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
        today = date.today()
        queryset = queryset.filter(
            created_date__range=[today, today])
    if threshold is None:
        threshold = 85
    queryset = DataSerializer(queryset, many=True, context={
                            'request': request}).data
    learning_status = State.objects.all()[0].progress
    result = {
        "List": queryset,
        "Learning_Status": learning_status
    }
    return Response(result, headers={"description": "SUCCESS"})


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
        "Original_image": data['original_image'],
        "Segmentation_image": data['segmentation_image'],
        "Box": bbox_data,
        "Ratio": ratio,
        "Margin_list": margin_list,
        "Cvat_url": data['cvat_url']
    }

    return Response(result, headers={"description": "SUCCESS"})


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


class BboxListView(ListCreateAPIView):
    queryset = Bbox.objects.all()
    serializer_class = BboxSerializer


class BboxRetrieveView(RetrieveUpdateDestroyAPIView):
    queryset = Bbox.objects.all()
    serializer_class = BboxSerializer


class MarginListView(ListCreateAPIView):
    queryset = Margin.objects.all()
    serializer_class = MarginSerializer


class MarginRetrieveView(RetrieveUpdateDestroyAPIView):
    queryset = Margin.objects.all()
    serializer_class = MarginSerializer
    

class ManualLogListView(ListCreateAPIView):
    queryset = ManualLog.objects.all()
    serializer_class = ManualLogSerializer

# schedule set
@api_view(['GET'])
def set_schedule(request):
    if request.method == 'GET':
        mode = State.objects.all()[0].mode
        return Response({"mode": mode})

# thr set
@api_view(['GET'])
def set_thr(request):
    if request.method == 'GET':
        thr = State.objects.all()[0].threshold * 100
        return Response({thr})

@api_view(['POST'])
def set_environment_variable(request):
    if request.method == 'POST':
        mode = request.META.get('HTTP_MODE')
        thr = request.META.get('HTTP_THRESHOLD')
        if mode == 'auto':
            s = State.objects.all()[0]
            s.mode = 'auto'
            s.save()
        elif mode == 'manual':
            s = State.objects.all()[0]
            s.mode = 'manual'
            s.save()
        elif mode == None:
            pass
        else:
            return Response({'400': 'Bad request'})
    
        if thr == None:
            pass
        elif 0 <= int(thr) <= 100:
            s = State.objects.all()[0]
            s.threshold = int(thr) / 100
            s.save()   
        else:
            return Response({'400': 'Bad request'})

        return Response({"200", f"ok"})


@api_view(['GET', 'POST'])
def self_train(request):
    if request.method == 'GET':
        s = State.objects.all()[0]
        progress = s.progress
        return Response({progress})
    
    if request.method == 'POST':
        rate = request.query_params.get('rate')
        # celery 구동 중지 기다리기
        while True:
            s = State.objects.all()[0]
            if s.work:
                time.sleep(1)
            else:
                s.work = True
                s.progress = 0
                s.save()
                break
        try:
            # 자가학습 실행
            os.system(f"python C:\\Users\\user\\Desktop\\IITP\\mmcv_laminate_alignment_system\\mlcc_self_train_train.py --rate {rate}")
            # os.system("sh C:/Users/user/Desktop/IITP/mmcv_laminate_alignment_system/run_self_train.sh")
            return Response({"200", f"ok"})
        except:
            return Response({'400': 'Bad request'})

        
@transaction.atomic
@api_view(['GET'])
def eval_self_train(request):
    # 모델 저장
    model_info = self_train_eval()
    for path, acc in model_info:
        print(path)
        name = path.split('seg')[1].split("/")
        name = f"{name[2]}_{name[1]}"
        InferencePath.objects.create(name = name, path = path, acc = acc)
    # 기본 inference 모델 설정
    highest = InferencePath.objects.all().order_by('-acc')[0]
    s = State.objects.all()[0]
    s.target_model = highest.name
    if InferencePath.objects.exclude(name = "Default").count() > 5:
        # 하위 모델 삭제
        models = InferencePath.objects.exclude(name = "Default").order_by('-acc')[5:]
        for model in models:
            path = model.path
            if os.path.exists(path):
                shutil.rmtree(path)
            
    # celery 구동 재개
    s = State.objects.all()[0]
    s.progress = 100
    s.work = False
    s.save()
    return Response({"200", f"ok"})


@api_view(['GET'])
def curr_inference_model(request): # 현재모델, 모델선택
    if request.method == 'GET':
        target_model = State.objects.all()[0].target_model
        return Response({target_model})

@api_view(['POST'])
def set_inference_model(request, name): # 현재모델, 모델선택
    if request.method == 'POST':
        if InferencePath.objects.filter(name=name).exists():
            s = State.objects.all()[0]
            s.target_model = name
            s.save()
            return Response({"200", f"ok"})
        else:
            return Response({"405", f"Model not found"})

        
# 전체 이미지 중 랜덤..?
@api_view(['GET'])
def sample_img(request):
    num = request.query_params.get('num')
    if num == None:
        num = "0"
    if num == "0":
        num = random.randint(1, 10)
    else:
        num = int(num)
    models = InferencePath.objects.exclude(name="Dafault").order_by('-acc')[:5].values("name", "path")
    default = InferencePath.objects.get(name="Default")
    root = "127.0.0.1:8000"
    res = {}
    res[default.name] = f"{root}/{default.path}/{num}.jpg"
    for model in models:
        name = model["name"]
        path = model["path"]
        res[name] = f"{root}/{path}/{num}.jpg"

    return Response(res)
