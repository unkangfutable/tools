import copy
import os
import random
import re
import sys

import Levenshtein
import requests, time, zipfile
from logzero import logger
import pypinyin
from urllib.parse import quote


class CopyManga:
    comic_info_host = 'https://api.copymanga.info'
    comic_source_host = 'https://hi77-overseas.mangafuna.xyz'

    def __init__(self, name, start=0, group=10):
        ...
        self.__source_session = requests.Session()
        self.__info_session = requests.Session()
        self.manga_chinese_name = name
        self.manga_name = ''
        self.manga_path = ""
        # 多少话打一次包
        self.group_rule = group
        # 从多少话开始下
        # offset 查询起点
        self.offset = start
        self.limit = 200
        self.chapter_list = []
        self.contents_type = 'default'  # 连载
        # self.contents_type = 'tankobon'  # 单行本
        self.header_format = {
            'user-agent': 'Dart/2.16 (dart:io)',
            'source': 'copyApp',
            'webp': "1",
            'region': "1",
            'version': '1.4.4',
            'authorization': 'Toen',
            'platform': "3"
        }

    @property
    def info_header(self):
        return self.header_format

    def search_manga(self):
        # 获取path_word 别名
        url = self.comic_info_host + f'/api/v3/search/comic?limit=21&offset=0&' \
                                     f'q={quote(self.manga_chinese_name)}&q_type=&platform=3'
        res = self.__info_session.get(url, headers=self.info_header)
        if res.status_code == 200:
            manga_list = res.json().get("results").get('list')
            # 一般是第一个
            if manga_list:
                target_manga = manga_list[0]
                self.manga_name = target_manga.get('path_word')
                self.manga_path = f'./mange/{self.manga_name}/'
            else:
                logger.error("暂无搜索结果")
                sys.exit(0)
        else:
            logger.error("search manga error")
        self.transform_name(chinese_name=self.manga_chinese_name)

    def manga_chapters(self):

        url = self.comic_info_host + f'/api/v3/comic/{self.manga_name}/group/{self.contents_type}/chapters?' \
                                     f'limit={self.limit}&offset={self.offset}&platform=3'
        res = self.__info_session.get(url, headers=self.info_header)
        if res.status_code == 200:
            chapters = res.json().get("results")
            self.chapter_list = chapters.get('list')
            if self.chapter_list:
                pass
                # 简化一下
                for index, char in enumerate(self.chapter_list):
                    self.chapter_list[index] = {'index': index, 'name': char.get("name"), 'uuid': char.get('uuid')}
                print(self.chapter_list)
            else:
                logger.error('get manga chapters info empty error')
        else:
            logger.error("get chapter request error")

    def download_pic(self):
        self.search_manga()
        self.manga_chapters()
        size = copy.deepcopy(self.group_rule)
        logger.info(f"每个压缩包{size}话")
        if self.chapter_list:
            for info_index, info in enumerate(self.chapter_list):
                chapter_id = info.get('uuid')
                chapter_name = info.get('name')
                # chapter_index = self.chapter_list[0].get('name')
                url = self.comic_info_host + f'/api/v3/comic/{self.manga_name}/chapter2/' + chapter_id + '?platform=3'
                source = self.__source_session.get(url, headers=self.info_header)
                if source.status_code == 200:
                    chapter_detail = source.json().get("results").get("chapter")
                    image_source = chapter_detail.get('contents')  # list[Dict]
                    image_words = chapter_detail.get("words")  # list[int]
                    if len(image_source) != len(image_words):
                        logger.error("图源和索引不符")
                    for index, source in enumerate(image_source):
                        url = source.get('url')
                        self.save_image(url, chapter_name, image_words[index]) if url else logger.error(
                            f"{chapter_id} url is empty")
                    logger.info(f"chapter list 的index {info_index}  size: {size}")
                    if info_index != 0 and info_index % int(size) == 0:
                        self.package(size)
                        self.group_rule += size
                else:
                    logger.error("get pic request error")
            # 将剩余的图片压缩
            left_pic = os.listdir(self.manga_path)
            if any(file.endswith('jpg') for file in left_pic):
                self.package(size, True)
        else:
            logger.error("chapter info is empty")

    def save_image(self, url, name, words):
        # 检查文件夹
        save_path = f'mange/{self.manga_name}'
        os.makedirs(save_path) if not os.path.exists(save_path) else ...
        res = self.__source_session.get(url)
        if res.status_code == 200 and len(res.content) > 100:
            ...
            pic_name = save_path + f'/{name}-{words}.jpg'
            with open(pic_name, 'wb')as file:
                file.write(res.content)
            logger.info(f"{pic_name} 下载完成")
            # time.sleep(random.randint(0, 2) + random.random())
        else:
            logger.error("get pic source error")

    def package(self, size, left=False):
        manga_path = self.manga_path
        unit = '话' if self.contents_type == 'default' else '卷'
        if not left:
            if self.group_rule > 1:
                # zip_name = f'第{self.offset + self.group_rule - size + 1}-{self.group_rule}{unit}.zip'
                zip_name = f'第{self.offset + self.group_rule - size + 1}-{self.offset + self.group_rule}{unit}.zip'
            else:
                zip_name = f'第{self.offset + self.group_rule}{unit}.zip'
        else:
            zip_name = f'第{self.offset + self.group_rule-size + 1}-最新{unit}.zip'
        zip_path = manga_path + zip_name
        folder_path = manga_path
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            # 遍历文件夹
            for foldername, subfolders, filenames in os.walk(folder_path):
                # 遍历文件名
                for filename in filenames:
                    # 只处理 JPG 文件
                    if filename.endswith('.webp') or filename.endswith('.jpg'):
                        # 获取文件的相对路径
                        relative_path = os.path.relpath(os.path.join(foldername, filename), folder_path)
                        # 将文件添加到 ZIP 中，使用相对路径作为 ZIP 中的文件名
                        zipf.write(os.path.join(foldername, filename), arcname=relative_path)
        # 清理已经打包的图片
        [os.remove(manga_path + pic) for pic in os.listdir(manga_path) if pic.endswith("webp") or pic.endswith('.jpg')]
        logger.info(f"{zip_name} 打包完成")

    def diff(self, pin_yin_name):
        # 计算Levenshtein距离
        distance = Levenshtein.distance(self.manga_name, pin_yin_name)
        # 计算相似度
        return 1 - (distance / max(len(self.manga_name), len(pin_yin_name)))

    def transform_name(self, chinese_name: str, ):
        pin_yin_name = CopyManga.remove_invalid_char(pypinyin.slug(chinese_name, style=pypinyin.NORMAL, separator=''))

        # 相似度较高就保用path_word ，相似度低就用chinese name的首字母拼音再次对照
        similarity = self.diff(pin_yin_name)
        if similarity < 0.5:
            pin_yin_name = CopyManga.remove_invalid_char(
                pypinyin.slug(chinese_name, style=pypinyin.INITIALS, separator=''))
            similarity = self.diff(pin_yin_name)
            if similarity < 0.5:
                logger.error(f'manga name 和path word相似度较低,需要人为判断:{self.manga_name}')
                sys.exit(0)
        logger.info(f'mange name similarity: {similarity * 100}%')
        logger.info(f'path word & translate : {self.manga_name}  & {pin_yin_name}')

    @staticmethod
    def remove_invalid_char(string: str):
        string = string.replace(' ', '')
        string = re.sub(r'[^a-zA-Z]', '', string)
        return string.lower()


if __name__ == '__main__':
    # os.makedirs('mange') if not os.path.exists('manga') else ...

    # f
    cp = CopyManga('R15+又怎样')
    cp.download_pic()
    # cp = CopyManga('woxinzhongdeyeshou')
    # cp.download_pic()
    # print(cp.remove_invalid_char('zhangyuPIECE ～wotuidehaizishilianjuren～'))
