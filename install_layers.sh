# see: https://github.com/awsdocs/aws-lambda-developer-guide/tree/main/sample-apps/blank-python
cd layers
rm -rf ./python *.zip
pip install -t ./python -r requirements.txt