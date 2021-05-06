# AWS Service Catalog Provisioning

If you have an existing AWS Service Catalog Portfolio, or would like to create the Product manually, follow these steps:

1. Sign in to the console with the data science account.
2. On the AWS Service Catalog console, under **Administration**, choose **Portfolios**.
3. Choose **Create a new portfolio**.
4. Name the portfolio `SageMaker Organization Templates`.
5. Download the [AB testing template](../ab-testing-pipeline.yml) to your computer.
6. Choose the new portfolio.
7. Choose **Upload a new product.**
8. For **Product name**¸ enter `A/B Testing Deployment Pipeline`.
9. For **Description**, enter `Amazon SageMaker Project for A/B Testing models`.
10. For **Owner**, enter your name.
11. Under **Version details**, for **Method**, choose **Use a template file**.
12. Choose **Upload a template**.
13. Upload the template you downloaded.
14. For **Version title**, enter `1.0`.

The remaining parameters are optional.

15. Choose **Review**.
16. Review your settings and choose **Create product**.
17. Choose **Refresh** to list the new product.
18. Choose the product you just created.
19. On the **Tags** tab, add the following tag to the product:
  - **Key** – `sagemaker:studio-visibility`
  - **Value** – `True`

Finally we need to add launch constraint and role permissions.

20. On the **Constraints** tab, choose Create constraint.
21. For **Product**, choose **AB Testing Pipeline** (the product you just created).
22. For **Constraint type**, choose **Launch**.
23. Under **Launch Constraint**, for **Method**, choose **Select IAM role**.
24. Choose **AmazonSageMakerServiceCatalogProductsLaunchRole**.
25. Choose **Create**.
26. On the **Groups, roles, and users** tab, choose **Add groups, roles, users**.
27. On the **Roles** tab, select the role you used when configuring your SageMaker Studio domain.
28. Choose **Add access**.

If you don’t remember which role you selected, in your data science account, go to the SageMaker console and choose **Amazon SageMaker Studio**. In the Studio **Summary** section, locate the attribute **Execution role**. Search for the name of this role in the previous step.