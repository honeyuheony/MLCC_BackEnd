from math import inf
import pathlib
from django.conf import settings
import os
import shutil
import sys
import cv2
import time
from celery import shared_task
import json
import pandas as pd
import numpy as np
from PIL import Image
from .models import Data, Bbox, Margin, ManualLog
from django.core.files.images import ImageFile
from datetime import datetime, date, timedelta
import subprocess 
sys.path.append("C:/Users/user/Desktop/IITP/mmcv_laminate_alignment_system")
from mlcc_django import auto_run_model, manual_run_model
from mlcc_systemkits.mlcc_system import MLCC_SYSTEM
import time
from multiprocessing import Pool

# db에 데이터 넣을 때 역순으로 넣기

running = False
results = []
@shared_task
def get_result():
    mode = getattr(settings, 'SYSTEM_MODE')
    if mode == 'auto':
        auto_get_result()
    else:
        manual_get_result()

def auto_get_result():
    global running
    if running:
        return -1
    running = True
    try:
        # 1. 모델 실행
        model_root = "C:/Users/user/Desktop/IITP/mmcv_laminate_alignment_system"
        server_root = "C:/Users/user/Desktop/IITP/MLCC_BE"
        dt = datetime.now().strftime('%Y%m%d%H%M%S')
        dir_path = f"{model_root}/mlcc_datasets/val_test"
        entries = os.scandir(dir_path)
        length = 0
        pic = []

        for entry in entries:
            length += 1
            pic.append(entry.path)

        if length != 0:
            # 2. 데이터 적재
            # python mlcc_inference.py
            # --source 'mlcc_datasets/val/' --remove_edge_bbox --project 'mmcl_results' --name 'demo1'
            global results
            results = auto_run_model(dt) 

            for i, result in enumerate(results):
                save_result(i)

        # 3. DB 적재한 모델 원본 데이터 삭제
        # val 내부 이미지
        # mmcl_results 내부 폴더

        entries = os.scandir(f'{model_root}/mlcc_datasets/val_test')
        for entry in entries:
            os.remove(entry.path)
        # entries = os.scandir(f'{model_root}/mmcl_results')
        # for entry in entries:
        #     shutil.rmtree(entry.path)

        # semaphore unlock
        running = False
    
    except:
        running = False


def manual_get_result():
    global running
    if running:
        return -1
    running = True
    try:
        model_root = "C:/Users/user/Desktop/IITP/mmcv_laminate_alignment_system"   
        server_root = "C:/Users/user/Desktop/IITP/MLCC_BE"
        dt = datetime.now().strftime('%Y%m%d%H%M%S')
        # 실행 경로 정하기
        dir_path = f"{model_root}/mlcc_datasets/smb"
        backup_path = f"{dir_path}/backup"

        first_create_time = datetime.now()
        first_create_pc = ''
        for path, subdirs, files in os.walk(dir_path):
            for name in files:
                t = os.path.getmtime(pathlib.PurePath(path, name))
                if t < first_create_time:
                    first_create_time = t
                    first_create_pc = path.split('smb/')[1].split('/')[0]

        pc_name = first_create_pc
        thr = getattr(settings, 'STANDARD_MARGIN_THR', 0.75)
        entries = os.scandir(dir_path)
        length = 0
        pic = []
        for entry in entries:
            length += 1
            pic.append(entry.path)
        # 2. 모델 실행 및 결과파일 생성
        if length != 0:
            global results
            results = manual_run_model(pc_name, thr) 
            os.makedirs(f'{dir_path+pc_name}/{dt}')
            for result in results:
                assessment = True
                for anotation in result['qa_result_list']:
                    if anotation['decision_result'] == False:
                        assessment = False
                        break

                f = open(f'{dir_path+pc_name}/{dt}/{result["img_basename"]}_{str(assessment)}', 'w')
                f.close()
                shutil.copyfile(f'{dir_path+pc_name}/{result["img_basename"]}', f'{backup_path}/{result["img_basename"]}')
                shutil.move(f'{dir_path+pc_name}/{result["img_basename"]}', {dir_path+pc_name}/{dt}/{result["img_basename"]})
                # 3. DB에 Log 적재
                log = ManualLog()
                log.filename = result["img_basename"]
                log.dt = datetime.now()

        # semaphore unlock
        running = False
    
    except:
        running = False


def save_result(i):
    result = results[i]
    server_root = "C:/Users/user/Desktop/IITP/MLCC_BE"
    img_name = result['img_basename']
    seg_name = img_name[0:len(img_name)-4] + '_seg.jpg'
    # seg_img = Image.fromarray(np.uint8(np.array(result['seg_img'])))
    # seg_img.save(dir_path + '/' + seg_name)
    img_dir = f"{server_root}/mlcc_be/media/data/{datetime.now().strftime('%m.%d')}"
    if not os.path.exists(img_dir):
        os.makedirs(img_dir)
    os.makedirs(f"{img_dir}/{result['img_basename'][0:len(result['img_basename'])-4]}")
    
    r = np.array(result['img0'])
    s = np.array(result['seg_img'])
    cv2.imwrite( f"{img_dir}/{result['img_basename'][0:len(result['img_basename'])-4]}/{img_name}", r)
    cv2.imwrite( f"{img_dir}/{result['img_basename'][0:len(result['img_basename'])-4]}/{seg_name}", s)
    #shutil.copyfile(dir_path + '/' + img_name, f"{img_dir}/{result['img_basename'][0:len(result['img_basename'])-4]}/{img_name}")
    #shutil.copyfile(dir_path + '/' + seg_name, f"{img_dir}/{result['img_basename'][0:len(result['img_basename'])-4]}/{seg_name}")
    start = time.time()
    d = Data()
    d.name = result['img_basename'][0:len(img_name)-4],
    d.original_image = f"{server_root}/mlcc_be/media/data/{datetime.now().strftime('%m.%d')}/{result['img_basename'][0:len(result['img_basename'])-4]}/{img_name}"
    d.segmentation_image = f"{server_root}/mlcc_be/media/data/{datetime.now().strftime('%m.%d')}/{result['img_basename'][0:len(result['img_basename'])-4]}/{seg_name}"
    d.created_date = date.today()
    d.cvat_url = f'http://localhost:8080/tasks/1/jobs/1?frame={i}'
    d.save()
    total_min_ratio = inf
    for bbox_id, anotation in enumerate(result['qa_result_list']):
        b = Bbox.objects.create(
            name=result['img_basename'][0:len(result['img_basename'])-4] + '_bbox_' + str(bbox_id+1),
            data=d,
            min_margin_ratio=anotation['min_margin_ratio']*100,
            box_width = (result['bboxes'][bbox_id][2] - result['bboxes'][bbox_id][0]),
            box_height = (result['bboxes'][bbox_id][3] - result['bboxes'][bbox_id][1]),
            box_x = result['bboxes'][bbox_id][0],
            box_y = result['bboxes'][bbox_id][1],
        )
        b.save()
        for i in range(len(anotation['first_lst'])):
            m = Margin.objects.create(
                name=result['img_basename'][0:len(result['img_basename'])-4] + '_bbox_' + str(bbox_id+1) + '_magrin_' + str(i+1),
                bbox=b,
                margin_x = result['bboxes'][bbox_id][0] + anotation['first_lst'][i],
                margin_y = result['bboxes'][bbox_id][1] + i,
                real_margin = anotation['real_margin'],
                margin_ratio = anotation['margin_ratio'][i]*100,
                margin_width = anotation['last_lst'][i]-anotation['first_lst'][i],
            )
            m.save()
        total_min_ratio = min(total_min_ratio, anotation['min_margin_ratio']) * 100
    d.margin_ratio = total_min_ratio
    d.save()
    print(time.time()-start)


# delete log, file
@shared_task
def reset_data():
    yesterday = datetime.today() - timedelta(days=1)
    log_list = ManualLog.objects.filter(dt__lte=yesterday)
    for log in log_list:
        log.delete()
    model_root = "C:/Users/user/Desktop/IITP/mmcv_laminate_alignment_system"  
    dir_path = f"{model_root}/mlcc_datasets/smb"
    for i in range(1, 6):
        path = f'{dir_path}/pc{i}'
    if os.path.exists(path):
        shutil.rmtree(path)
        os.mkdir(path)
