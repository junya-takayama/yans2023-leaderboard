# -*-coding:utf-8-*-

import argparse

import pandas as pd
from sklearn.metrics import ndcg_score


def convert_to_submit_format(df, score_column, mode="pred"):
    output_list = []
    for product_idx in sorted(set(df["product_idx"])):
        df_product = df[df["product_idx"] == product_idx]
        scores = [
            {"review_idx": i, mode + "_score": s}
            for i, s in zip(df_product["review_idx"], df_product[score_column])
        ]
        output_list.append({"product_idx": product_idx, mode + "_list": scores})
    return pd.DataFrame(output_list)

def calc_ndcg(df_true, df_pred):
    df = pd.merge(df_true, df_pred, on="product_idx")
    sum_ndcg = 0
    for df_dict in df.to_dict("records"):
        df_eval = pd.merge(
            pd.DataFrame(df_dict["pred_list"]),
            pd.DataFrame(df_dict["true_list"]),
            on="review_idx",
        )
        ndcg = ndcg_score([df_eval["true_score"]], [df_eval["pred_score"]], k=5)
        sum_ndcg += ndcg
    return {"ndcg@5": sum_ndcg / len(df)}


def main(args):
    df_pred = pd.read_json(args.pred_file, orient="records", lines=True)
    df = pd.read_json(args.true_file, orient="records", lines=True)
    assert len(set(df["product_id"])) == len(set(df_pred) and set(df["product_id"]))

    if "leader_board" in args.true_file:
        df_use = df[df["sets"] == "leader_board-private"]
    elif "final_result"in args.true_file:
        df_use = df[df["sets"] == "final_result-private"]
    df_true = convert_to_submit_format(df_use, "helpful_votes", "true")

    print(calc_ndcg(df_true, df_pred))



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred_file", type=str, default="./submit/submit_leader_board.jsonl")
    parser.add_argument("--true_file", type=str, default="./dataset_private/leader_board.jsonl")
    args = parser.parse_args()
    main(args)
