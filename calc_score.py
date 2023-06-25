# -*-coding:utf-8-*-

import argparse

import pandas as pd
import sacrebleu
import MeCab
from rouge_score import rouge_scorer
from rouge_score.tokenizers import Tokenizer


class DataMismatchError(Exception):
    pass


class MeCabTokenizer(Tokenizer):
    def tokenize(self, text: str) -> str:
        m = MeCab.Tagger("-Owakati")
        return m.parse(text).strip()


def _calc_bleu(df: pd.DataFrame) -> float:
    hypotheses: list[str] = df["title_generated"].tolist()
    org_ref_clumn_name = "title_org"
    additional_ref_column_names = {"title_ne1", "title_ne2", "title_ne3"}

    if additional_ref_column_names in set(df.columns):
        references: list[list[str]] = df[
            {org_ref_clumn_name} | additional_ref_column_names
        ].fillna("").to_numpy().T.tolist()
    else:
        references: list[list[str]] = df[[org_ref_clumn_name]].to_numpy().T.tolist()

    return sacrebleu.corpus_bleu(hypotheses, references, tokenize="ja-mecab").score


def _calc_rouge(df: pd.DataFrame) -> float:
    tokenizer = MeCabTokenizer()
    hypotheses: list[str] = df["title_generated"].tolist()
    references: list[str] = df["title_org"].tolist()
    scorer = rouge_scorer.RougeScorer(["rouge1"], tokenizer=tokenizer)
    denom = len(references)
    return 100 * sum([scorer.score(ref, hypo)["rouge1"].fmeasure for ref, hypo in zip(references, hypotheses)]) / denom


def _calc_kwd(df: pd.DataFrame) -> float:
    keywords_list: list[list[str]] = df["kw"].str.split(" ")
    hypotheses: list[str] = df["title_generated"].tolist()

    def _calc_kwd_onerecord(text, keywords: list[str]) -> float:
        return sum([keyword in text for keyword in keywords]) / len(keywords)

    denom = len(keywords_list)
    return 100 * sum([_calc_kwd_onerecord(hypo, keywords) for hypo, keywords in zip(hypotheses, keywords_list)]) / denom


def calc_scores(df_true: pd.DataFrame, df_pred: pd.DataFrame) -> dict[str, float]:
    df = pd.merge(df_true, df_pred, on="asset_id", how="inner")

    if len(df) != len(df_true):
        raise DataMismatchError("正解データと提出データで対応が取れない行があります")

    bleu_score = _calc_bleu(df)
    rouge_score = _calc_rouge(df)
    kwd_score = _calc_kwd(df)
    hmean_score = 3 / (1 / bleu_score + 1 / rouge_score + 1 / kwd_score)

    return {
        "BLEU-4": _calc_bleu(df),
        "Rouge-1": _calc_rouge(df),
        "Kwd": _calc_kwd(df),
        "Overall": hmean_score
    }


def main(args):
    df_pred = pd.read_csv(args.pred_file).fillna("")
    df_true = pd.read_csv(args.true_file).fillna("")
    print(calc_scores(df_true, df_pred))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-file", type=str, default="./submit/submit_leader_board.csv")
    parser.add_argument("--true-file", type=str, default="./dataset_private/leader_board.csv")
    args = parser.parse_args()
    main(args)
