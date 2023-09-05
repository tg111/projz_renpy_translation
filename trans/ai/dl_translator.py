import logging
import os.path
from typing import List, Tuple

import tqdm
from prettytable import PrettyTable

from store.index import project_index
from trans.base import translator
from config.config import default_config
import dl_translate as dlt

from util.file import exists_dir
from util.misc import my_input

AVAILABLE_MODELS = ['m2m100', 'mbart50', 'nllb200']


class trans_wrapper(translator):
    def __init__(self, proj: project_index, model_family=AVAILABLE_MODELS[0]):
        save_dir = default_config.get_global('MODEL_SAVE_PATH')
        self.model_family = model_family
        self.proj = proj
        if save_dir is not None:
            model_path = os.path.join(save_dir, model_family)
            assert exists_dir(model_path), f'The path ({model_path}) not a valid directory!'
            self.mt = dlt.TranslationModel(model_path, model_family="m2m100")

        else:
            self.mt = dlt.TranslationModel(model_family)

    def determine_translation_target(self):
        ava_langs = list(self.mt.available_languages())
        ava_indexes = list(range(len(ava_langs)))

        table = PrettyTable(
            ['Index', 'Language'])
        for i, lang in enumerate(ava_langs):
            table.add_row([f'{i}', lang])
        print(table)
        while True:
            args = my_input(
                'Please set the translation target (enter two language indexes from above table, like "0 1" which means that translating text from source language 0 into language 1),\n'
                ' or enter Q/q to exit): ')
            args = args.strip()
            args = [c.strip() for c in args.split() if c.strip() != '']
            if len(args) >= 1:
                if len(args) == 1:
                    if args[0].lower() == 'q':
                        return False
                if len(args) == 2:
                    try:
                        s, t = int(args[0]), int(args[1])
                        assert s in ava_indexes and t in ava_indexes, f'{s} or {t} is out of range!'
                        self.source = ava_langs[s]
                        self.target = ava_langs[t]
                        return True
                    except Exception as e:
                        print(e)

    def determine_batch_size(self):
        while True:
            args = my_input(
                'Please set the batch size for translation (lager value brings faster translation but consumes more (GPU) menmory)\n'
                ' or enter Q/q to exit): ')
            args = args.strip()
            if args.lower() == 'q':
                return False
            try:
                bz = int(args)
                assert bz > 0, f'{bz} should be greter than 0!'
                self.batch_size = bz
                return True
            except Exception as e:
                print(e)

    def translate_all(self, lang: str):
        if self.proj.untranslation_size(lang) <= 0:
            logging.info(f'All texts in {self.proj.full_name} of language {lang} are translated!')
            return
        untranslated_lines = self.proj.untranslated_lines(lang)

        yes = self.determine_translation_target()
        if not yes:
            logging.info(f'Stopped by user')
            return
        logging.info(f'Set the translation target: {self.source} -> {self.target}')
        self.determine_batch_size()
        if not yes:
            logging.info(f'Stopped by user')
            return
        batch_size = self.batch_size
        logging.info(f'Set the batch size to {batch_size}')
        batches = []
        for i in range(0, len(untranslated_lines), batch_size):
            batches.append(untranslated_lines[i: min(i + batch_size, len(untranslated_lines))])
        logging.info(
            f'Starting translating {len(untranslated_lines)} untranslated line(s)')

        for b in tqdm.tqdm(batches, desc=f'Translating'):
            translated_lines = []
            tids, texts = [], []
            for tid, text in b:
                if text.strip() == '':
                    logging.warning(f'Empty text [{text}] found!')
                    translated_lines.append((tid, text))
                    continue
                tids.append(tid)
                texts.append(text)
            res = self.translate_batch(texts)
            assert len(res) == len(tids)
            for tid, newtext in zip(tids, res):
                translated_lines.append((tid, '@@' + newtext))
            self.proj.update(translated_lines, lang)
        self.proj.save_by_default()

    def translate(self, rawtext: str):
        res = self.mt.translate(rawtext, self.source, self.target, batch_size=1, verbose=False)
        return res

    def translate_batch(self, rawtexts: List[str]):
        res = self.mt.translate(rawtexts, self.source, self.target, batch_size=len(rawtexts), verbose=False)
        return res

    def close(self):
        del self.mt


if __name__ == '__main__':
    p = project_index.init_from_dir(r'translated/tmp_renpy_game/game', 'a', 'a', False)
    t = trans_wrapper(p, 'm2m100')
    t.translate_all('chinese')
    p.apply_by_default()
    pass
