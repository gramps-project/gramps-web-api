#! /usr/bin/env python3

"""Script to rename all objects in an S3 bucket from `name` to `tree-id/name`."""


import argparse
import os

import boto3


def rename_objects(bucket_name: str, tree: str) -> None:
    """Rename all objects in a bucket by appending `tree/`."""
    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        config=boto3.session.Config(
            s3={"addressing_style": "path"}, signature_version="s3v4"
        ),
    )

    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name)

    for page in pages:
        for obj in page["Contents"]:
            old_key = obj["Key"]
            if not old_key.startswith(f"{tree}/"):
                new_key = f"{tree}/{old_key}"
                print(f"Renaming object {old_key} to {new_key}")
                client.copy_object(
                    Bucket=bucket_name,
                    CopySource={"Bucket": bucket_name, "Key": old_key},
                    Key=new_key,
                )
            client.delete_object(Bucket=bucket_name, Key=old_key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename all objects in an S3 bucket")
    parser.add_argument(
        "bucket_name",
        metavar="BUCKET_NAME",
        help="The name of the bucket to rename objects in",
    )
    parser.add_argument(
        "tree",
        metavar="TREE",
        help="The name of the directory to move the objects into",
    )

    args = parser.parse_args()

    rename_objects(bucket_name=args.bucket_name, tree=args.tree.rstrip("/"))
