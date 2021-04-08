import setuptools


with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="amazon_sagemaker_ab_testing_infra",
    version="0.0.1",
    description="An empty CDK Python app",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="author",
    package_dir={"": "infra"},
    packages=setuptools.find_packages(where="infra"),
    install_requires=[
        "aws-cdk.core==1.94.1",
        "aws-cdk.aws-apigateway==1.94.1",
        "aws_cdk.aws_codebuild==1.94.1",
        "aws_cdk.aws_codecommit==1.94.1",
        "aws_cdk.aws_codepipeline==1.94.1",
        "aws_cdk.aws_codepipeline_actions==1.94.1",
        "aws_cdk.aws_dynamodb==1.94.1",
        "aws-cdk.aws-events==1.94.1",
        "aws-cdk.aws-events-targets==1.94.1",
        "aws-cdk.aws-iam==1.94.1",
        "aws-cdk.aws-lambda==1.94.1",
        "aws-cdk.aws-s3-notifications==1.94.1",
    ],
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: JavaScript",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
)
